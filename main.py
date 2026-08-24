import network
import mixiot
import usocket
import uos
import gc

UPLOAD_DIR = '/uploads'
CHUNK_SIZE = 512

CONFIG = {}

def load_config():
    global CONFIG
    try:
        with open('config.txt', 'r') as f:
            content = f.read()
        
        for line in content.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                CONFIG[key.strip()] = value.strip()
        return True
    except:
        print("找不到配置")
        return False

def save_config():
    global CONFIG
    try:
        lines = []
        for k, v in CONFIG.items():
            lines.append('%s:%s' % (k, v))
        with open('config.txt', 'w') as f:
            f.write('\n'.join(lines))
        return True
    except:
        return False

def url_decode(s):
    result = bytearray()
    i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                result.append(int(s[i+1:i+3], 16))
                i += 3
            except:
                result.append(ord(s[i]))
                i += 1
        elif s[i] == '+':
            result.append(32)
            i += 1
        else:
            result.append(ord(s[i]))
            i += 1
    return result.decode('utf-8')

def parse_post_data(body):
    params = {}
    parts = body.split('&')
    for part in parts:
        if '=' in part:
            k, v = part.split('=', 1)
            params[url_decode(k)] = url_decode(v)
    return params

def is_safe_char(c):
    code = ord(c)
    if 48 <= code <= 57:
        return True
    if 65 <= code <= 90:
        return True
    if 97 <= code <= 122:
        return True
    if 0x4E00 <= code <= 0x9FFF:
        return True
    if c in ' .-_':
        return True
    return False

def produce_wifi():
    if not load_config():
        return
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    wifi_ssid = CONFIG.get('WIFI', 'CMCC-PRGC')
    wifi_pwd = CONFIG.get('WIFIPWD', '5bt6h7sx')
    
    mixiot.wlan_connect(wifi_ssid, wifi_pwd)
    
    import time
    for _ in range(10):
        if wlan.isconnected():
            break
        time.sleep(1)
    
    if wlan.isconnected():
        print('设备IP:', wlan.ifconfig()[0])
        init_server()
    else:
        print('WiFi failed：网络连接故障')

def init_server():
    try:
        uos.mkdir(UPLOAD_DIR)
    except:
        pass
    
    addr = usocket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = usocket.socket()
    s.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(2)
    
    print_exec = CONFIG.get('Print_exec', '家庭存储服务已经启动！请及时修改config.txt文件避免出错。')
    print(print_exec)
    
    while True:
        gc.collect()
        try:
            conn, addr = s.accept()
            conn.settimeout(15)
            data = conn.recv(1024)
            if data:
                handle_request(conn, data)
            conn.close()
        except Exception as e:
            print('Error:', e)
            try:
                conn.close()
            except:
                pass

def handle_request(conn, data):
    try:
        lines = data.split(b'\r\n')
        req = lines[0].decode('utf-8', 'ignore')
        method, path, _ = req.split(' ')
        
        if path == '/':
            send_html(conn)
        elif path == '/setup' and method == 'POST':
            handle_setup(conn, data)
        elif path == '/list':
            files = []
            try:
                for f in uos.listdir(UPLOAD_DIR):
                    st = uos.stat(UPLOAD_DIR + '/' + f)
                    files.append('{"n":"%s","s":%d}' % (f, st[6]))
            except:
                pass
            json = '[' + ','.join(files) + ']'
            conn.send(b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n')
            conn.send(json.encode())
        elif path.startswith('/d/'):
            fn = url_decode(path[3:])
            try:
                with open(UPLOAD_DIR + '/' + fn, 'rb') as f:
                    conn.send(b'HTTP/1.0 200 OK\r\nContent-Disposition: attachment\r\n\r\n')
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        conn.send(chunk)
            except:
                conn.send(b'HTTP/1.0 404\r\n\r\nNot found')
        elif path.startswith('/x/'):
            fn = url_decode(path[3:])
            try:
                uos.remove(UPLOAD_DIR + '/' + fn)
                conn.send(b'HTTP/1.0 200 OK\r\n\r\nOK')
            except:
                conn.send(b'HTTP/1.0 500\r\n\r\nError')
        elif path == '/u':
            handle_upload(conn, data)
        else:
            conn.send(b'HTTP/1.0 404\r\n\r\n')
    except Exception as e:
        print('Req error:', e)
        conn.send(b'HTTP/1.0 500\r\n\r\n')

def handle_setup(conn, data):
    try:
        header_end = data.find(b'\r\n\r\n')
        while header_end == -1:
            more = conn.recv(512)
            if not more:
                break
            data += more
            header_end = data.find(b'\r\n\r\n')
            
        hdr = data[:header_end].decode('utf-8', 'ignore')
        content_length = 0
        for line in hdr.split('\r\n'):
            if line.lower().startswith('content-length:'):
                content_length = int(line.split(':', 1)[1].strip())
                break
                
        body = data[header_end + 4:]
        while len(body) < content_length:
            more = conn.recv(512)
            if not more:
                break
            body += more
            
        params = parse_post_data(body.decode('utf-8', 'ignore'))
        
        web_name = params.get('WebName', 'Home')
        top_color = params.get('TOPCOLOR', '#01b48d')
        iot_name = params.get('loTName', 'ESP32-C3')
        
        if iot_name == '其他':
            iot_name = params.get('custom_iot', 'ESP')
            
        CONFIG['WebName'] = web_name
        CONFIG['TOPCOLOR'] = top_color
        CONFIG['loTName'] = iot_name
        CONFIG['RESIGER'] = 'True'
        
        save_config()
        
        conn.send(b'HTTP/1.0 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nOK')
    except Exception as e:
        print('Setup error:', e)
        conn.send(b'HTTP/1.0 500\r\n\r\nError')

def handle_upload(conn, data):
    try:
        header_end = data.find(b'\r\n\r\n')
        while header_end == -1:
            more = conn.recv(512)
            if not more:
                break
            data += more
            header_end = data.find(b'\r\n\r\n')
            
        if header_end == -1:
            conn.send(b'HTTP/1.0 400\r\n\r\n')
            return
            
        hdr = data[:header_end].decode('utf-8', 'ignore')
        
        content_length = 0
        for line in hdr.split('\r\n'):
            if line.lower().startswith('content-length:'):
                content_length = int(line.split(':', 1)[1].strip())
                break
                
        if 'boundary=' not in hdr:
            conn.send(b'HTTP/1.0 400\r\n\r\n')
            return
            
        boundary = ('--' + hdr.split('boundary=')[1].split('\r\n')[0].strip()).encode()
        
        buffer = data[header_end + 4:]
        
        while len(buffer) < content_length:
            more = conn.recv(1024)
            if not more:
                break
            buffer += more
            
        parts = buffer.split(boundary)
        
        for part in parts:
            if b'filename=' in part:
                p_idx = part.find(b'\r\n\r\n')
                if p_idx == -1:
                    continue
                p1 = part[:p_idx].decode('utf-8', 'ignore')
                p2 = part[p_idx + 4:]
                
                if 'filename="' not in p1:
                    continue
                    
                fn = p1.split('filename="')[1].split('"')[0]
                fn = url_decode(fn)
                
                safe = ''
                for c in fn:
                    if is_safe_char(c):
                        safe += c
                    else:
                        safe += '_'
                safe = safe.strip()
                if not safe:
                    safe = 'unnamed'
                    
                final = safe
                cnt = 1
                while True:
                    try:
                        uos.stat(UPLOAD_DIR + '/' + final)
                        if '.' in safe:
                            parts_name = safe.rsplit('.', 1)
                            final = parts_name[0] + '_%d.' % cnt + parts_name[1]
                        else:
                            final = safe + '_%d' % cnt
                        cnt += 1
                    except:
                        break
                        
                if p2.endswith(b'\r\n'):
                    p2 = p2[:-2]
                    
                with open(UPLOAD_DIR + '/' + final, 'wb') as f:
                    f.write(p2)
                    
                conn.send(b'HTTP/1.0 200 OK\r\n\r\nOK')
                return
                
        conn.send(b'HTTP/1.0 400\r\n\r\n')
    except Exception as e:
        print('Upload error:', e)
        conn.send(b'HTTP/1.0 500\r\n\r\n')

def send_html(conn):
    web_name = CONFIG.get('WebName', '云上存储')
    iot_name = CONFIG.get('loTName', 'ESP32')
    top_color = CONFIG.get('TOPCOLOR', '#01b48d')
    resiger = CONFIG.get('RESIGER', 'False')
    
    conn.send(b'HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n')
    
    if resiger.lower() == 'false':
        html_wizard = b'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>欢迎使用 HomeFileServer!</title>
<style>
:root{--primary:''' + top_color.encode('utf-8') + b''';--background:#f5f5f5;--surface:#fff;--text:#212121;--text-secondary:#757575}
*{margin:0;padding:0;box-sizing:border-box;font-family:system-ui,-apple-system,sans-serif}
body{background:var(--background);color:var(--text);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px}
.card{background:var(--surface);border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,0.1);padding:24px;width:100%;max-width:400px}
.title{font-size:22px;font-weight:600;color:var(--primary);margin-bottom:8px;text-align:center}
.subtitle{font-size:14px;color:var(--text-secondary);margin-bottom:24px;text-align:center}
.form-group{margin-bottom:16px}
label{display:block;font-size:14px;font-weight:500;margin-bottom:6px;color:var(--text)}
input[type="text"],select,input[type="color"]{width:100%;padding:10px 12px;border:1px solid #ccc;border-radius:8px;font-size:14px;outline:none}
input[type="color"]{height:40px;padding:2px;cursor:pointer}
input[type="text"]:focus,select:focus{border-color:var(--primary)}
.btn{width:100%;padding:12px;background:var(--primary);color:#fff;border:none;border-radius:20px;font-size:16px;font-weight:500;cursor:pointer;margin-top:12px;transition:0.3s}
.btn:hover{opacity:0.9}
#customIotGroup{display:none}
</style>
</head>
<body>
<div class="card">
<div class="title">欢迎使用 HomeFileServer!</div>
<div class="subtitle">请完成初始化配置以继续使用</div>
<form id="setupForm" onsubmit="submitSetup(event)">
<div class="form-group">
<label for="webName">家庭名称</label>
<input type="text" id="webName" name="WebName" value="''' + web_name.encode('utf-8') + b'''" placeholder="请输入家庭名称" required>
</div>
<div class="form-group">
<label for="topColor">主题颜色</label>
<input type="color" id="topColor" name="TOPCOLOR" value="''' + top_color.encode('utf-8') + b'''">
</div>
<div class="form-group">
<label for="iotName">主机名称</label>
<select id="iotName" name="loTName" onchange="checkIotSelect(this)">
<option value="ESP32-C3">ESP32-C3</option>
<option value="ESP32-S3">ESP32-S3</option>
<option value="其他">其他</option>
</select>
</div>
<div class="form-group" id="customIotGroup">
<label for="customIot">自定义主机名称</label>
<input type="text" id="customIot" name="custom_iot" placeholder="请输入主机名称">
</div>
<button type="submit" class="btn">下一步</button>
</form>
</div>
<script>
function checkIotSelect(elem){
    var cg = document.getElementById("customIotGroup");
    if(elem.value === "其他"){
        cg.style.display = "block";
        document.getElementById("customIot").required = true;
    }else{
        cg.style.display = "none";
        document.getElementById("customIot").required = false;
    }
}
function submitSetup(e){
    e.preventDefault();
    var form = document.getElementById("setupForm");
    var formData = new FormData(form);
    var params = new URLSearchParams();
    for(var pair of formData.entries()){
        params.append(pair[0], pair[1]);
    }
    fetch("/setup", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: params.toString()
    }).then(function(r){
        if(r.ok){
            location.reload();
        }else{
            alert("配置保存失败");
        }
    }).catch(function(){
        alert("网络错误");
    });
}
</script>
</body>
</html>'''
        conn.send(html_wizard)
        return

    html_part1 = b'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>File Server</title>
<style>
:root{--primary:''' + top_color.encode('utf-8') + b''';--primary-dark:''' + top_color.encode('utf-8') + b''';--surface:#fff;--background:#f5f5f5;--text:#212121;--text-secondary:#757575;--error:#b3261e}
*{margin:0;padding:0;box-sizing:border-box;font-family:system-ui,-apple-system,sans-serif}
body{background:var(--background);color:var(--text)}
.appbar{height:56px;background:var(--surface);box-shadow:0 2px 4px rgba(0,0,0,0.1);display:flex;align-items:center;padding:0 16px;position:sticky;top:0;z-index:100}
.appbar-title{font-size:20px;font-weight:500;margin-left:16px;flex:1}
.appbar-subtitle{font-size:14px;color:var(--text-secondary);margin-left:8px}
.btn-icon{width:40px;height:40px;border:none;background:transparent;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--text-secondary)}
.btn-icon:hover{background:rgba(0,0,0,0.05)}
.drawer{position:fixed;left:0;top:0;bottom:0;width:280px;background:var(--surface);box-shadow:2px 0 8px rgba(0,0,0,0.1);transform:translateX(-100%);transition:0.3s;z-index:200;padding:16px}
.drawer.open{transform:translateX(0)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,0.5);opacity:0;visibility:hidden;transition:0.3s;z-index:150}
.overlay.show{opacity:1;visibility:visible}
.container{padding:16px;max-width:900px;margin:0 auto}
.card{background:var(--surface);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.1);margin-bottom:16px;overflow:hidden}
.card-header{padding:16px;border-bottom:1px solid rgba(0,0,0,0.05);display:flex;align-items:center;gap:8px}
.card-title{font-size:16px;font-weight:500}
.card-content{padding:16px}
.upload-area{border:2px dashed var(--primary);border-radius:8px;padding:32px;text-align:center;cursor:pointer;background:rgba(1,180,141,0.05);transition:0.3s}
.upload-area:hover{background:rgba(1,180,141,0.1)}
.upload-area.dragover{background:rgba(1,180,141,0.2)}
.upload-icon{font-size:48px;margin-bottom:8px}
.upload-text{font-size:16px;font-weight:500;margin-bottom:4px}
.upload-hint{font-size:13px;color:var(--text-secondary)}
.file-list{display:flex;flex-direction:column;gap:8px}
.file-item{display:flex;align-items:center;padding:12px;background:rgba(0,0,0,0.03);border-radius:8px}
.file-item:hover{background:rgba(1,180,141,0.1)}
.file-icon{width:40px;height:40px;background:rgba(1,180,141,0.15);border-radius:8px;display:flex;align-items:center;justify-content:center;margin-right:12px;font-size:20px;color:var(--primary)}
.file-info{flex:1;min-width:0}
.file-name{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-size{font-size:12px;color:var(--text-secondary);margin-top:2px}
.file-actions{display:flex;gap:4px}
.badge{background:rgba(0,0,0,0.08);padding:2px 8px;border-radius:12px;font-size:12px;color:var(--text-secondary)}
.empty{text-align:center;padding:40px;color:var(--text-secondary)}
.empty-icon{font-size:64px;margin-bottom:16px;opacity:0.5}
.snackbar{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(100px);background:#322f35;color:#fff;padding:14px 24px;border-radius:4px;opacity:0;transition:0.3s;z-index:300}
.snackbar.show{transform:translateX(-50%) translateY(0);opacity:1}
.dialog{position:fixed;inset:0;background:rgba(0,0,0,0.5);display:none;align-items:center;justify-content:center;z-index:400}
.dialog.show{display:flex}
.dialog-content{background:var(--surface);border-radius:16px;padding:24px;min-width:280px;max-width:90%}
.dialog-title{font-size:20px;font-weight:500;margin-bottom:16px}
.dialog-text{color:var(--text-secondary);font-size:14px;margin-bottom:24px;word-break:break-all}
.dialog-actions{display:flex;justify-content:flex-end;gap:8px}
.btn{padding:10px 24px;border:none;border-radius:20px;font-size:14px;font-weight:500;cursor:pointer;text-transform:uppercase;letter-spacing:0.5px}
.btn-text{background:transparent;color:var(--primary)}
.btn-text:hover{background:rgba(1,180,141,0.1)}
.btn-filled{background:var(--primary);color:#fff}
.btn-filled:hover{background:var(--primary-dark)}
.btn-filled.error{background:var(--error)}
#fileInput{display:none}
</style>
</head>
<body>
<div class="appbar">
<button class="btn-icon" onclick="toggleDrawer()"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em"><path fill="currentColor" d="M11.025 21.95q-1.9-.2-3.537-1.037t-2.863-2.175T2.7 15.675T2 12q0-3.925 2.613-6.75t6.412-3.2v2.025q-2.975.375-5 2.613T4 12t2.025 5.313t5 2.612zm0-4.95v-6.175l-2.6 2.6L7.025 12l5-5l5 5l-1.425 1.4l-2.575-2.575V17zm2 4.95v-2.025q1.1-.125 2.088-.55t1.812-1.075l1.425 1.45q-1.125.9-2.475 1.475t-2.85.725M16.9 5.7q-.825-.65-1.8-1.075t-2.075-.55V2.05q1.5.15 2.85.725T18.35 4.25zm2.85 12.625L18.325 16.9q.65-.825 1.075-1.812T19.95 13h2.025q-.15 1.5-.737 2.85t-1.488 2.475m.2-7.325q-.125-1.1-.55-2.087T18.325 7.1l1.425-1.425q.9 1.125 1.488 2.475t.737 2.85z"/></svg></button>
<div class="appbar-title">''' + web_name.encode('utf-8') + b'''</div>
<div class="appbar-subtitle">''' + iot_name.encode('utf-8') + b''' @ <span id="ip"></span></div>
<button class="btn-icon" onclick="doRefresh()"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em"><path fill="currentColor" d="M6 12.05q0 1.125.425 2.188T7.75 16.2l.25.25V15q0-.425.288-.712T9 14t.713.288T10 15v4q0 .425-.288.713T9 20H5q-.425 0-.712-.288T4 19t.288-.712T5 18h1.75l-.4-.35q-1.3-1.15-1.825-2.625T4 12.05Q4 9.7 5.2 7.787T8.425 4.85q.35-.2.738-.025t.512.575q.125.375-.012.75t-.488.575q-1.45.8-2.312 2.213T6 12.05m12-.1q0-1.125-.425-2.187T16.25 7.8L16 7.55V9q0 .425-.288.713T15 10t-.712-.288T14 9V5q0-.425.288-.712T15 4h4q.425 0 .713.288T20 5t-.288.713T19 6h-1.75l.4.35q1.225 1.225 1.788 2.663T20 11.95q0 2.35-1.2 4.263t-3.225 2.937q-.35.2-.737.025t-.513-.575q-.125-.375.013-.75t.487-.575q1.45-.8 2.313-2.212T18 11.95"/></svg></button>
</div>

<div class="overlay" id="overlay" onclick="toggleDrawer()"></div>
<div class="drawer" id="drawer">
<div style="font-size:20px;font-weight:500;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid rgba(0,0,0,0.1)">上传文件</div>
<div class="upload-area" onclick="document.getElementById('fileInput').click()" ondrop="drop(event)" ondragover="over(event)" ondragleave="leave(event)">
<div class="upload-icon"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em"><path fill="currentColor" d="M6.5 20q-2.275 0-3.887-1.575T1 14.575q0-1.95 1.175-3.475T5.25 9.15q.625-2.3 2.5-3.725T12 4q2.925 0 4.963 2.038T19 11q1.725.2 2.863 1.488T23 15.5q0 1.875-1.312 3.188T18.5 20H13q-.825 0-1.412-.587T11 18v-5.15L9.4 14.4L8 13l4-4l4 4l-1.4 1.4l-1.6-1.55V18h5.5q1.05 0 1.775-.725T21 15.5t-.725-1.775T18.5 13H17v-2q0-2.075-1.463-3.538T12 6T8.463 7.463T7 11h-.5q-1.45 0-2.475 1.025T3 14.5t1.025 2.475T6.5 18H9v2zm5.5-7"/></svg></div>
<div class="upload-text">点击或拖拽上传</div>
<div class="upload-hint">支持中文与空格</div>
</div>
<input type="file" id="fileInput" onchange="doUpload(this.files[0])">
</div>

<div class="container">
<div class="card">
<div class="card-header">
<span style="font-size:20px"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="1em" height="1em"><path fill="#eab308" d="M4 20q-.825 0-1.412-.587T2 18V6q0-.825.588-1.412T4 4h5.175q.4 0 .763.15t.637.425L12 6h8q.825 0 1.413.588T22 8v10q0 .825-.587 1.413T20 20z"/></svg></span>
<div class="card-title">文件列表</div>
<span class="badge" id="count">0</span>
</div>
<div class="card-content">
<div id="fileList"><div class="empty"><div class="empty-icon">📂</div><div>暂无文件</div></div></div>
</div>
</div>
</div>

<div class="snackbar" id="snackbar">操作成功</div>

<div class="dialog" id="dialog" onclick="if(event.target==this)closeDialog()">
<div class="dialog-content">
<div class="dialog-title">删除文件</div>
<div class="dialog-text" id="dialogText"></div>
<div class="dialog-actions">
<button class="btn btn-text" onclick="closeDialog()">取消</button>
<button class="btn btn-filled error" onclick="doDelete()">删除</button>
</div>
</div>
</div>

<script>
'''
    conn.send(html_part1)
    
    conn.send(b'''
var target=null;
document.getElementById("ip").textContent=location.host;

function toggleDrawer(){
    var d=document.getElementById("drawer");
    var o=document.getElementById("overlay");
    if(d.classList.contains("open")){
        d.classList.remove("open");
        o.classList.remove("show");
    }else{
        d.classList.add("open");
        o.classList.add("show");
    }
}

function show(msg){
    var sb=document.getElementById("snackbar");
    sb.textContent=msg;
    sb.classList.add("show");
    setTimeout(function(){
        sb.classList.remove("show");
    },2500);
}

function over(e){
    e.preventDefault();
    e.currentTarget.classList.add("dragover");
}

function leave(e){
    e.currentTarget.classList.remove("dragover");
}

function drop(e){
    e.preventDefault();
    e.currentTarget.classList.remove("dragover");
    doUpload(e.dataTransfer.files[0]);
}

function fmt(b){
    if(b<1024)return b+"B";
    if(b<1048576)return(b/1024).toFixed(1)+"KB";
    return(b/1048576).toFixed(1)+"MB";
}

function loadFiles(){
    fetch("/list").then(function(r){
        return r.json();
    }).then(function(files){
        var h="";
        document.getElementById("count").textContent=files.length;
        if(files.length==0){
            h="<div class=\\"empty\\"><div class=\\"empty-icon\\">📂</div><div>暂无文件</div></div>";
        }else{
            for(var i=0;i<files.length;i++){
                var f=files[i];
                var enc=encodeURIComponent(f.n);
                var name=f.n.replace(/"/g,"&quot;");
                h=h+"<div class=\\"file-item\\"><div class=\\"file-icon\\">📄</div><div class=\\"file-info\\"><div class=\\"file-name\\" title=\\""+name+"\\">"+f.n+"</div><div class=\\"file-size\\">"+fmt(f.s)+"</div></div><div class=\\"file-actions\\"><button class=\\"btn-icon\\" onclick=\\"downloadFile(\\'"+enc+"\\')\\">⬇️</button><button class=\\"btn-icon\\" onclick=\\"askDelete(\\'"+enc+"\\')\\" style=\\"color:var(--error)\\">🗑️</button></div></div>";
            }
        }
        document.getElementById("fileList").innerHTML=h;
    }).catch(function(e){
        show("加载失败");
    });
}

function doRefresh(){
    loadFiles();
}

function doUpload(file){
    if(!file)return;
    var d=new FormData();
    d.append("file",file);
    fetch("/u",{method:"POST",body:d}).then(function(){
        show("上传成功");
        toggleDrawer();
        loadFiles();
    }).catch(function(){
        show("上传失败");
    });
}

function downloadFile(n){
    window.open("/d/"+n);
}

function askDelete(n){
    target=n;
    document.getElementById("dialogText").textContent="确定要删除 "+decodeURIComponent(n)+" 吗？";
    document.getElementById("dialog").classList.add("show");
}

function closeDialog(){
    document.getElementById("dialog").classList.remove("show");
    target=null;
}

function doDelete(){
    if(!target)return;
    fetch("/x/"+target).then(function(){
        show("已删除");
        loadFiles();
    }).catch(function(){
        show("删除失败");
    });
    closeDialog();
}

loadFiles();
setInterval(loadFiles,5000);
</script>
</body>
</html>
''')

produce_wifi()
