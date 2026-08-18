import os
import sys
import json
import time
import asyncio
import subprocess
import threading
from typing import List, Dict, Any
from io import BytesIO, StringIO

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import pandas as pd

# Cấu hình encoding console UTF-8 cho Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

app = FastAPI(title="Antigravity Data Suite UI", version="2.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Quản lý danh sách kết nối WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()
active_subprocesses: List[subprocess.Popen] = []

# Đảm bảo file config.json luôn tồn tại
def ensure_config_exists():
    config_file = "config.json"
    example_file = "config.json.example"
    if not os.path.exists(config_file):
        if os.path.exists(example_file):
            try:
                with open(example_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

ensure_config_exists()

def load_config_dict():
    ensure_config_exists()
    config_file = "config.json"
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_config_dict(cfg):
    config_file = "config.json"
    cfg["USE_MY_CHROME_PROFILE"] = False
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return True

# Phục hồi tệp JSON an toàn
def safe_read_records(file_path):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            try:
                data = json.loads(content)
            except json.JSONDecodeError as jde:
                if "Extra data" in str(jde):
                    data = json.loads(content[:jde.pos].strip())
                else:
                    return []
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Phân phát Static Files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/style.css")
async def get_style_css():
    return FileResponse(os.path.join(STATIC_DIR, "style.css"))

@app.get("/app.js")
async def get_app_js():
    return FileResponse(os.path.join(STATIC_DIR, "app.js"))

# API Cấu hình
@app.get("/api/config")
async def get_config():
    return load_config_dict()

@app.post("/api/config")
async def update_config(cfg: Dict[str, Any]):
    save_config_dict(cfg)
    await manager.broadcast("[+] Đã cập nhật file config.json từ Web UI.")
    return {"status": "success", "message": "Đã lưu cấu hình thành công!"}

# API Dữ liệu & Export
@app.get("/api/records")
async def get_records():
    cfg = load_config_dict()
    output_file = cfg.get("output_file", "hotels.json")
    records = safe_read_records(output_file)
    return {"output_file": output_file, "total": len(records), "records": records}

@app.get("/api/records/export/excel")
async def export_excel():
    cfg = load_config_dict()
    output_file = cfg.get("output_file", "hotels.json")
    records = safe_read_records(output_file)
    if not records:
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu để xuất Excel.")

    df = pd.DataFrame(records)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    output.seek(0)
    
    excel_filename = output_file.replace('.json', '.xlsx')
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={excel_filename}"}
    )

@app.get("/api/records/export/csv")
async def export_csv():
    cfg = load_config_dict()
    output_file = cfg.get("output_file", "hotels.json")
    records = safe_read_records(output_file)
    if not records:
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu để xuất CSV.")

    df = pd.DataFrame(records)
    csv_str = df.to_csv(index=False, encoding='utf-8-sig')
    csv_filename = output_file.replace('.json', '.csv')
    return StreamingResponse(
        StringIO(csv_str),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={csv_filename}"}
    )

@app.get("/api/records/export/json")
async def export_json():
    cfg = load_config_dict()
    output_file = cfg.get("output_file", "hotels.json")
    if not os.path.exists(output_file):
        raise HTTPException(status_code=404, detail="File kết quả JSON chưa tồn tại.")
    return FileResponse(output_file, media_type="application/json", filename=output_file)

# WEBSOCKET LOG SERVER
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# TASK RUNNER SUBPROCESS CONTROL
def run_command_stream(cmd, task_name, loop):
    venv_python = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable
    full_cmd = [python_exe] + cmd
    
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            cwd=BASE_DIR,
            env=env
        )
        active_subprocesses.append(proc)
        
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(f"[*] [{task_name}] Đã khởi chạy tiến trình PID {proc.pid}..."),
            loop
        )

        for line in iter(proc.stdout.readline, ''):
            if line:
                cleaned_line = line.rstrip()
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(cleaned_line),
                    loop
                )
        proc.wait()
        if proc in active_subprocesses:
            active_subprocesses.remove(proc)

        asyncio.run_coroutine_threadsafe(
            manager.broadcast(f"[+] [{task_name}] Tiến trình PID {proc.pid} đã hoàn thành!"),
            loop
        )
    except Exception as e:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(f"[!] [{task_name}] Lỗi chạy tiến trình: {e}"),
            loop
        )

# TASKS CONTROL ENDPOINTS
@app.post("/api/tasks/start/map_3way")
async def start_map_3way():
    loop = asyncio.get_event_loop()
    def launch_staggered():
        for m, tag in [("3way_p1", "MAP_P1"), ("3way_p2", "MAP_P2"), ("3way_p3", "MAP_P3")]:
            threading.Thread(target=run_command_stream, args=(["map_scraper.py", f"--mode={m}"], tag, loop), daemon=True).start()
            time.sleep(0.8)
    threading.Thread(target=launch_staggered, daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Cào Google Maps song song 3 luồng (P1 -> P3)!"}

@app.post("/api/tasks/start/map_4way")
async def start_map_4way():
    loop = asyncio.get_event_loop()
    def launch_staggered():
        for m, tag in [("4way_p1", "MAP_P1"), ("4way_p2", "MAP_P2"), ("4way_p3", "MAP_P3"), ("4way_p4", "MAP_P4")]:
            threading.Thread(target=run_command_stream, args=(["map_scraper.py", f"--mode={m}"], tag, loop), daemon=True).start()
            time.sleep(0.8)
    threading.Thread(target=launch_staggered, daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Cào Google Maps song song 4 luồng (P1 -> P4)!"}

@app.post("/api/tasks/start/map_5way")
async def start_map_5way():
    loop = asyncio.get_event_loop()
    def launch_staggered():
        for m, tag in [("5way_p1", "MAP_P1"), ("5way_p2", "MAP_P2"), ("5way_p3", "MAP_P3"), ("5way_p4", "MAP_P4"), ("5way_p5", "MAP_P5")]:
            threading.Thread(target=run_command_stream, args=(["map_scraper.py", f"--mode={m}"], tag, loop), daemon=True).start()
            time.sleep(0.8)
    threading.Thread(target=launch_staggered, daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Cào Google Maps song song 5 luồng (P1 -> P5)!"}

@app.post("/api/tasks/start/map_dual")
async def start_map_dual():
    return await start_map_5way()

@app.post("/api/tasks/start/email_dual")
async def start_email_dual():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["email_harvester.py", "--mode=top"], "EMAIL_TOP", loop), daemon=True).start()
    threading.Thread(target=run_command_stream, args=(["email_harvester.py", "--mode=bottom"], "EMAIL_BOTTOM", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Quét Email song song 2 luồng (TOP & BOTTOM)!"}

@app.post("/api/tasks/start/phone_dual")
async def start_phone_dual():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["phone_harvester.py", "--mode=top"], "PHONE_TOP", loop), daemon=True).start()
    threading.Thread(target=run_command_stream, args=(["phone_harvester.py", "--mode=bottom"], "PHONE_BOTTOM", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Cào & Bổ Sung SĐT song song 2 luồng Chromium (TOP & BOTTOM)!"}

@app.post("/api/tasks/start/cat_repair")
async def start_cat_repair():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["category_repairer.py", "--mode=top"], "CAT_TOP", loop), daemon=True).start()
    threading.Thread(target=run_command_stream, args=(["category_repairer.py", "--mode=bottom"], "CAT_BOTTOM", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Dò CategoryName song song 2 luồng (TOP & BOTTOM)!"}

@app.post("/api/tasks/start/info_repair")
async def start_info_repair():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["info_repairer.py"], "INFO_REPAIR", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Sửa dữ liệu N/A!"}



@app.post("/api/tasks/start/mismatch_repair")
async def start_mismatch_repair():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["mismatch_repairer.py"], "MISMATCH_REPAIR", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Công Cụ Sửa Lỗi Lệch Dòng Title & URL!"}

@app.post("/api/tasks/start/booking_harvester")
async def start_booking_harvester():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["booking_harvester.py"], "BOOKING_HARVESTER", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt Cào Booking.com Trực Tiếp (Stage 1)!"}

@app.post("/api/tasks/start/ai_checking")
async def start_ai_checking():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_command_stream, args=(["ai_checking.py"], "AI_CHECKING", loop), daemon=True).start()
    return {"status": "success", "message": "Đã kích hoạt AI Checking (Google Gemini API)!"}

@app.post("/api/tasks/stop")
async def stop_tasks():
    killed = 0
    for proc in list(active_subprocesses):
        try:
            proc.kill()
            killed += 1
        except Exception:
            pass
    active_subprocesses.clear()
    await manager.broadcast("[!] Đã dừng tất cả các tiến trình cào dữ liệu.")
    return {"status": "success", "message": f"Đã dừng {killed} tiến trình cào dữ liệu."}

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
