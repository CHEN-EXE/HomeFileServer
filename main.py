import network
import mixiot
import usocket
import uos
import gc

UPLOAD_DIR = '/uploads'
CHUNK_SIZE = 512

# 全局配置变量
CONFIG = {}

def load_config():
    """读取 config.txt 配置文件"""
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
    # 加载配置
    if not load_config():
        return
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # 联网配置
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
    
    # 配置启动信息
    print_exec = CONFIG.get('Print_exec', '家庭存储服务已经启动！请及时修改config.txt文件避免出错。')
    print(print_exec)
    
    while True:
        gc.collect()
        try:
            conn, addr = s.accept()
            conn.settimeout(15)
            data = conn.recv(4096)
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

def handle_upload(conn, data):
    try:
        idx = data.find(b'\r\n\r\n')
        if idx == -1:
            conn.send(b'HTTP/1.0 400\r\n\r\n')
            return
        
        hdr = data[:idx].decode('utf-8', 'ignore')
        body = data[idx+4:]
        
        if 'boundary=' not in hdr:
            conn.send(b'HTTP/1.0 400\r\n\r\n')
            return
        
        bd = '--' + hdr.split('boundary=')[1].split('\r\n')[0].strip()
        parts = body.split(bd.encode())
        
        for part in parts:
            if b'filename=' in part:
                p1, p2 = part.split(b'\r\n\r\n', 1)
                p1 = p1.decode('utf-8', 'ignore')
                
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
                
                with open(UPLOAD_DIR + '/' + final, 'wb') as f:
                    f.write(p2.rstrip(b'\r\n-'))
                
                conn.send(b'HTTP/1.0 200 OK\r\n\r\nOK')
                return
        
        conn.send(b'HTTP/1.0 400\r\n\r\n')
    except Exception as e:
        print('Upload error:', e)
        conn.send(b'HTTP/1.0 500\r\n\r\n')

def send_html(conn):
    # 获取配置
    web_name = CONFIG.get('WebName', '云上存储')
    iot_name = CONFIG.get('loTName', 'ESP32')
    
    conn.send(b'HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n')
    
    # 分段化
    html_part1 = b'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>File Server</title>
<style>
:root{--primary:#01b48d;--primary-dark:#018a6d;--surface:#fff;--background:#f5f5f5;--text:#212121;--text-secondary:#757575;--error:#b3261e}
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
<button class="btn-icon" onclick="toggleDrawer()">☰</button>
<div class="appbar-title">''' + web_name.encode('utf-8') + b'''</div>
<div class="appbar-subtitle">''' + iot_name.encode('utf-8') + b''' @ <span id="ip"></span></div>
<button class="btn-icon" onclick="doRefresh()">↻</button>
</div>

<div class="overlay" id="overlay" onclick="toggleDrawer()"></div>
<div class="drawer" id="drawer">
<div style="font-size:20px;font-weight:500;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid rgba(0,0,0,0.1)">上传文件</div>
<div class="upload-area" onclick="document.getElementById('fileInput').click()" ondrop="drop(event)" ondragover="over(event)" ondragleave="leave(event)">
<div class="upload-icon">📤</div>
<div class="upload-text">点击或拖拽上传</div>
<div class="upload-hint">支持中文与空格</div>
</div>
<input type="file" id="fileInput" onchange="doUpload(this.files[0])">
</div>

<div class="container">
<div class="card">
<div class="card-header">
<span style="font-size:20px">📁</span>
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
<div class="dialog-title">🗑️ 删除文件</div>
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
    
    # JavaScript
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
