import shutil
import os
import json
from datetime import datetime
from collections import Counter

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

import firebase_admin
from firebase_admin import credentials, auth

import cupones      # IA Visión de Cupones
import database     # Base de Datos de CuponIA

# ==============================================================================
# INICIALIZACIÓN
# ==============================================================================
if not firebase_admin._apps:
    try:
        firebase_json_str = os.environ.get("FIREBASE_JSON")
        if firebase_json_str:
            cert_dict = json.loads(firebase_json_str)
            cred = credentials.Certificate(cert_dict)
            firebase_admin.initialize_app(cred)
            print("✅ [BOOT] Firebase Security CuponIA: ACTIVE")
        elif os.path.exists("firebase_credentials.json"):
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"⚠️ [BOOT] Error Firebase: {e}")

app = FastAPI(title="CuponIA Enterprise - Smart Coupon Wallet")
database.inicializar_db()

async def get_current_user(authorization: str = Header(...)):
    try:
        if not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Token inválido")
        token = authorization.split("Bearer ")[1]
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception:
        raise HTTPException(status_code=401, detail="Sesión expirada")

# ==============================================================================
# ASSETS PWA
# ==============================================================================
@app.get("/manifest.json")
async def get_manifest():
    return JSONResponse({
        "name": "CuponIA", "short_name": "CuponIA", "start_url": "/", "display": "standalone",
        "background_color": "#004d40", "theme_color": "#004d40",
        "icons":[{"src": "/cuponia_icon.png", "sizes": "512x512", "type": "image/png"}]
    })

@app.get("/cuponia_icon.png")
async def get_icon():
    if os.path.exists("cuponia_icon.png"): return FileResponse("cuponia_icon.png")
    return JSONResponse(status_code=404, content={"error": "Icono no encontrado"})

@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy():
    return """<html><body><h1>Política de Privacidad de CuponIA</h1><p>CuponIA solo usa la cámara para escanear tus cupones y vales de descuento de supermercado. Tus datos se guardan de forma privada y segura.</p></body></html>"""

# ==============================================================================
# FRONTEND INTERACTIVO (PWA + JsBarcode)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    html_content = r"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <title>CuponIA - Cartera Inteligente de Supermercado</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
        <link rel="manifest" href="/manifest.json">
        <meta name="theme-color" content="#004d40">
        
        <!-- Librería ultra-ligera para generar códigos de barra láser en pantalla -->
        <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.5/dist/JsBarcode.all.min.js"></script>

        <style>
            :root { --primary: #004d40; --primary-light: #00796b; --accent: #ff6f00; --bg: #f4f6f8; --card: #ffffff; }
            body { font-family: 'Segoe UI', Roboto, sans-serif; background: var(--bg); margin: 0; color: #263238; display: flex; justify-content: center; min-height: 100vh; padding-bottom: 50px; }
            .app-container { width: 100%; max-width: 600px; padding: 15px; display: none; }
            
            #loginScreen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; width: 100%; text-align: center; }
            .login-btn { background: white; color: #444; border: 1px solid #ddd; padding: 15px 30px; border-radius: 50px; font-weight: bold; font-size: 16px; display: flex; align-items: center; gap: 10px; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
            
            header { text-align: center; margin-top: 50px; margin-bottom: 20px; }
            h1 { margin: 0; color: var(--primary); font-size: 34px; letter-spacing: -1px; font-weight: 900; }
            .tagline { color: #546e7a; font-size: 13px; margin-top: 5px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
            
            /* Tarjeta de Ahorro Acumulado */
            .savings-card { background: linear-gradient(135deg, #004d40, #00796b); color: white; padding: 20px; border-radius: 20px; text-align: center; box-shadow: 0 10px 25px rgba(0,77,64,0.3); margin-bottom: 20px; }
            .savings-amount { font-size: 36px; font-weight: 900; margin: 5px 0; color: #a7ffeb; }
            
            .card { background: white; padding: 20px; border-radius: 20px; box-shadow: 0 5px 20px rgba(0,0,0,0.04); margin-bottom: 20px; }
            h3 { margin-top: 0; color: var(--primary); font-size: 17px; display: flex; align-items: center; gap: 8px; }
            
            .btn { width: 100%; padding: 15px; border: none; border-radius: 14px; font-size: 15px; font-weight: 700; color: white; cursor: pointer; transition: 0.2s; box-sizing: border-box; text-align: center; }
            .btn-green { background: linear-gradient(135deg, #00796b, #004d40); box-shadow: 0 4px 12px rgba(0,77,64,0.3); }
            .btn-orange { background: linear-gradient(135deg, #ff6f00, #ffa000); box-shadow: 0 4px 12px rgba(255,111,0,0.3); }
            
            /* Filtros de Supermercados (Chips) */
            .filters-container { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 15px; scrollbar-width: none; }
            .chip { background: #e0f2f1; color: #004d40; padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; border: 1px solid #b2dfdb; }
            .chip.active { background: var(--primary); color: white; border-color: var(--primary); }

            /* Tarjetas de Cupones */
            .coupon-item { background: white; border-radius: 16px; border: 1px solid #e0e0e0; margin-bottom: 15px; padding: 16px; position: relative; overflow: hidden; display: flex; flex-direction: column; gap: 8px; }
            .coupon-item.used { opacity: 0.5; background: #fafafa; }
            .coupon-badge-market { background: #e0f2f1; color: #00796b; padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 800; text-transform: uppercase; display: inline-block; }
            .coupon-title { font-size: 17px; font-weight: bold; color: #263238; margin: 4px 0; }
            .coupon-conditions { font-size: 12px; color: #78909c; }
            
            /* Semáforo de Caducidad */
            .tag-urgent { background: #ffebee; color: #c62828; font-weight: 800; font-size: 11px; padding: 4px 8px; border-radius: 6px; }
            .tag-ok { background: #e8f5e9; color: #2e7d32; font-weight: 800; font-size: 11px; padding: 4px 8px; border-radius: 6px; }
            .tag-expired { background: #eeeeee; color: #9e9e9e; text-decoration: line-through; font-size: 11px; padding: 4px 8px; border-radius: 6px; }
            
            /* Modal Código de Barras (Pantalla de Caja) */
            #barcodeModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 3000; justify-content: center; align-items: center; }
            .barcode-box { background: white; padding: 25px 20px; border-radius: 20px; width: 90%; max-width: 360px; text-align: center; }
            
            /* Cámara WebRTC */
            #cameraModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #000; z-index: 2000; flex-direction: column; justify-content: space-between; }
            .camera-header { padding: 15px 20px; display: flex; justify-content: space-between; color: white; background: rgba(0,0,0,0.6); }
            .camera-viewport { position: relative; width: 100%; flex: 1; display: flex; justify-content: center; align-items: center; }
            #cameraVideo { width: 100%; height: 100%; object-fit: cover; }
            .camera-guide { position: absolute; width: 85%; height: 50%; border: 2px dashed #00e676; border-radius: 16px; box-shadow: 0 0 0 9999px rgba(0,0,0,0.5); pointer-events: none; }
            .camera-footer { padding: 25px 0 45px 0; background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center; gap: 30px; }
            .btn-shutter { width: 75px; height: 75px; border-radius: 50%; background: white; border: 5px solid var(--primary); cursor: pointer; }
        </style>
    </head>
    <body>
        
        <!-- PANTALLA LOGIN -->
        <div id="loginScreen">
            <h1 style="color:#004d40">CuponIA</h1>
            <p style="color:#666">Tu Cartera Inteligente de Descuentos</p>
            <button class="login-btn" onclick="loginWithGoogle()">
                <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="20">
                <span>Acceder con Google</span>
            </button>
        </div>

        <!-- APP PRINCIPAL -->
        <div id="appScreen" class="app-container">
            <header>
                <h1>CuponIA</h1>
                <div class="tagline">Ahorro Inteligente de Supermercado</div>
            </header>

            <!-- TARJETA AHORRO TOTAL -->
            <div class="savings-card">
                <div style="font-size:13px; font-weight:bold; text-transform:uppercase;">💰 Tu Ahorro Disponible</div>
                <div id="totalSavings" class="savings-amount">0.00 €</div>
                <div style="font-size:11px; opacity:0.8;">En cupones activos listos para canjear</div>
            </div>

            <!-- ESCÁNER DE CUPONES -->
            <div class="card">
                <h3>📷 Digitalizar Cupón / Vale</h3>
                <input type="file" id="fileInput" accept="image/*" onchange="subirGaleria()" style="display:none">
                <div style="display:flex; flex-direction:column; gap:10px;">
                    <button id="btnScan" class="btn btn-green" onclick="abrirCamara()">📷 Escanear Cupón de Papel</button>
                    <button class="btn" style="background:#e0f2f1; color:#004d40;" onclick="document.getElementById('fileInput').click()">📁 Subir desde Galería</button>
                </div>
            </div>

            <!-- MI CARTERA DE CUPONES -->
            <div class="card">
                <h3>🛍️ Mis Cupones Guardados</h3>
                
                <!-- Filtro por Supermercado -->
                <div class="filters-container">
                    <div class="chip active" onclick="filterMarket(this, 'todos')">Todos</div>
                    <div class="chip" onclick="filterMarket(this, 'carrefour')">Carrefour</div>
                    <div class="chip" onclick="filterMarket(this, 'dia')">Dia</div>
                    <div class="chip" onclick="filterMarket(this, 'lidl')">Lidl</div>
                    <div class="chip" onclick="filterMarket(this, 'mercadona')">Mercadona</div>
                    <div class="chip" onclick="filterMarket(this, 'eroski')">Eroski</div>
                    <div class="chip" onclick="filterMarket(this, 'alcampo')">Alcampo</div>
                </div>

                <div id="couponsList">Cargando cupones...</div>
            </div>
        </div>

        <!-- MODAL CÓDIGO DE BARRAS (PARA MOSTRAR EN CAJA) -->
        <div id="barcodeModal">
            <div class="barcode-box">
                <h3 id="modalMarket" style="margin:0; justify-content:center; text-transform:uppercase; color:#004d40;">Carrefour</h3>
                <p id="modalTitle" style="font-weight:bold; font-size:15px; margin:5px 0 15px 0;">3€ en Pescadería</p>
                
                <!-- Aquí se dibuja el código de barras nítido para el escáner láser -->
                <div style="background:white; padding:10px; border-radius:10px; border:1px solid #ddd;">
                    <svg id="barcodeSvg" style="width:100%;"></svg>
                </div>

                <p style="font-size:11px; color:#666; margin:10px 0;">Acerca la pantalla al lector de caja</p>
                <button class="btn btn-green" style="margin-bottom:8px;" onclick="marcarCanjeadoModal()">✅ Ya lo he usado</button>
                <button class="btn" style="background:#eee; color:#333;" onclick="cerrarBarcode()">Cerrar</button>
            </div>
        </div>

        <!-- MODAL CÁMARA IN-APP (WebRTC + Linterna) -->
        <div id="cameraModal">
            <div class="camera-header">
                <button id="btnTorch" style="background:none; border:none; font-size:20px; color:white;" onclick="toggleTorch()">🔦</button>
                <span style="font-weight:bold;">Escanear Vale / Cupón</span>
                <button style="background:none; border:none; font-size:20px; color:white;" onclick="cerrarCamara()">✕</button>
            </div>
            <div class="camera-viewport">
                <video id="cameraVideo" autoplay playsinline></video>
                <div class="camera-guide"></div>
            </div>
            <div class="camera-footer">
                <button id="btnCapturar" class="btn-shutter" onclick="capturarFoto()"></button>
            </div>
        </div>
        <canvas id="cameraCanvas" style="display:none;"></canvas>

        <!-- JAVASCRIPT CORE -->
        <script type="module">
            import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
            import { getAuth, signInWithPopup, GoogleAuthProvider, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

            // Configuración Firebase (Reutilizamos las llaves seguras)
            const app = initializeApp({ apiKey: "AIzaSyCFB2fuuwpP-YJNzF9oFebutaK4ZHoM9tc", authDomain: "lotia-f4e4f.firebaseapp.com", projectId: "lotia-f4e4f" });
            const auth = getAuth();
            const provider = new GoogleAuthProvider();

            window.userToken = null;
            window.allCoupons = [];
            window.selectedMarket = 'todos';
            window.currentCouponIdModal = null;

            onAuthStateChanged(auth, async (u) => {
                if (u) {
                    window.userToken = await u.getIdToken();
                    document.getElementById('loginScreen').style.display = 'none';
                    document.getElementById('appScreen').style.display = 'block';
                    window.loadCoupons();
                } else {
                    document.getElementById('loginScreen').style.display = 'flex';
                    document.getElementById('appScreen').style.display = 'none';
                }
            });

            window.loginWithGoogle = () => signInWithPopup(auth, provider).catch(e => alert(e.message));

            async function authFetch(url, opts = {}) {
                if (!window.userToken) return alert("Sesión expirada");
                opts.headers = opts.headers || {};
                opts.headers['Authorization'] = 'Bearer ' + window.userToken;
                return fetch(url, opts);
            }

            // CARGAR Y RENDERIZAR CUPONES
            window.loadCoupons = async () => {
                try {
                    const res = await authFetch('/cupones');
                    window.allCoupons = await res.json();
                    window.renderCoupons();
                } catch(e) {}
            };

            window.filterMarket = (el, market) => {
                document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
                el.classList.add('active');
                window.selectedMarket = market;
                window.renderCoupons();
            };

            window.renderCoupons = () => {
                const list = document.getElementById('couponsList');
                let html = "";
                let totalSavings = 0;
                const today = new Date(); today.setHours(0,0,0,0);

                const filtered = window.allCoupons.filter(c => {
                    if (window.selectedMarket === 'todos') return true;
                    return c.supermercado.toLowerCase().includes(window.selectedMarket);
                });

                if (filtered.length === 0) {
                    list.innerHTML = "<div style='text-align:center; padding:30px; color:#90a4ae;'>No tienes cupones aquí. ¡Escanea uno nuevo!</div>";
                    document.getElementById('totalSavings').innerText = "0.00 €";
                    return;
                }

                filtered.forEach(c => {
                    let expBadge = "";
                    let isExpired = false;

                    // Calcular Caducidad
                    if (c.fecha_caducidad && c.fecha_caducidad.includes('/')) {
                        const [d, m, y] = c.fecha_caducidad.split('/');
                        const expDate = new Date(y, m-1, d);
                        const diff = Math.ceil((expDate - today) / (1000 * 60 * 60 * 24));

                        if (diff < 0) {
                            expBadge = `<span class="tag-expired">Caducado el ${c.fecha_caducidad}</span>`;
                            isExpired = true;
                        } else if (diff === 0) {
                            expBadge = `<span class="tag-urgent">🔥 ¡CADUCA HOY!</span>`;
                        } else if (diff <= 3) {
                            expBadge = `<span class="tag-urgent">⏳ Quedan ${diff} días</span>`;
                        } else {
                            expBadge = `<span class="tag-ok">Válido hasta ${c.fecha_caducidad}</span>`;
                        }
                    }

                    if (!c.is_used && !isExpired) {
                        totalSavings += c.importe || 0;
                    }

                    html += `
                    <div class="coupon-item ${c.is_used ? 'used' : ''}">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span class="coupon-badge-market">${c.supermercado}</span>
                            ${expBadge}
                        </div>
                        <div class="coupon-title">${c.titulo}</div>
                        <div class="coupon-conditions">${c.condiciones || 'Sin condiciones adicionales'}</div>
                        
                        <div style="display:flex; gap:10px; margin-top:8px;">
                            ${c.codigo_barras ? `<button class="btn btn-orange" style="padding:10px; font-size:13px;" onclick="mostrarBarcode(${c.id}, '${c.supermercado}', '${c.titulo}', '${c.codigo_barras}')">🎟️ USAR EN CAJA</button>` : ''}
                            <button class="btn" style="background:#eceff1; color:#37474f; padding:10px; width:auto;" onclick="borrarCupon(${c.id})">🗑️</button>
                        </div>
                    </div>`;
                });

                list.innerHTML = html;
                document.getElementById('totalSavings').innerText = totalSavings.toFixed(2) + " €";
            };

            // MOSTRAR CÓDIGO DE BARRAS EN GRANDE (JSBARCODE)
            window.mostrarBarcode = (id, market, title, code) => {
                window.currentCouponIdModal = id;
                document.getElementById('modalMarket').innerText = market;
                document.getElementById('modalTitle').innerText = title;
                document.getElementById('barcodeModal').style.display = 'flex';

                try {
                    // Genera el código de barras en formato Code128 automáticamente
                    JsBarcode("#barcodeSvg", code, {
                        format: "CODE128",
                        width: 2.5,
                        height: 80,
                        displayValue: true,
                        fontSize: 16
                    });
                } catch(e) {
                    alert("Código no compatible con lector de barras");
                }
            };

            window.cerrarBarcode = () => document.getElementById('barcodeModal').style.display = 'none';

            window.marcarCanjeadoModal = async () => {
                if (!window.currentCouponIdModal) return;
                await authFetch(`/cupones/${window.currentCouponIdModal}/toggle_used`, {method:'POST'});
                window.cerrarBarcode();
                window.loadCoupons();
            };

            window.borrarCupon = async (id) => {
                if (confirm("¿Eliminar este cupón de tu cartera?")) {
                    await authFetch(`/cupones/${id}`, {method:'DELETE'});
                    window.loadCoupons();
                }
            };

            // CÁMARA IN-APP WEBRTC
            let cameraStream = null;
            let torchActive = false;

            window.abrirCamara = async () => {
                const modal = document.getElementById('cameraModal');
                const video = document.getElementById('cameraVideo');
                modal.style.display = 'flex';
                torchActive = false;

                try {
                    cameraStream = await navigator.mediaDevices.getUserMedia({
                        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
                        audio: false
                    });
                    video.srcObject = cameraStream;
                } catch (err) {
                    alert("No se pudo abrir la cámara. Sube la foto desde la galería.");
                    window.cerrarCamara();
                    document.getElementById('fileInput').click();
                }
            };

            window.cerrarCamara = () => {
                if (cameraStream) {
                    cameraStream.getTracks().forEach(track => track.stop());
                    cameraStream = null;
                }
                document.getElementById('cameraModal').style.display = 'none';
            };

            window.toggleTorch = async () => {
                if (!cameraStream) return;
                const track = cameraStream.getVideoTracks()[0];
                const capabilities = track.getCapabilities ? track.getCapabilities() : {};
                if (!capabilities.torch) return alert("Flash no disponible");
                torchActive = !torchActive;
                await track.applyConstraints({ advanced: [{ torch: torchActive }] });
            };

            window.capturarFoto = () => {
                const video = document.getElementById('cameraVideo');
                const canvas = document.getElementById('cameraCanvas');
                canvas.width = video.videoWidth || 1280;
                canvas.height = video.videoHeight || 720;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                canvas.toBlob(async (blob) => {
                    window.cerrarCamara();
                    const fd = new FormData();
                    fd.append("file", blob, "cupon.jpg");
                    await window.procesarSubida(fd);
                }, 'image/jpeg', 0.92);
            };

            window.subirGaleria = async () => {
                const inp = document.getElementById('fileInput');
                if (!inp.files.length) return;
                const fd = new FormData();
                fd.append("file", inp.files[0]);
                await window.procesarSubida(fd);
                inp.value = "";
            };

            window.procesarSubida = async (formData) => {
                const btn = document.getElementById('btnScan');
                btn.innerHTML = "⏳ Analizando cupón con IA...";
                btn.disabled = true;

                try {
                    const res = await authFetch('/scan', {method:'POST', body:formData});
                    const d = await res.json();
                    if (d.ok) {
                        alert(`✅ ¡Guardado! ${d.data.titulo_descuento} (${d.data.supermercado})`);
                        window.loadCoupons();
                    } else {
                        alert("No se pudo leer el cupón con claridad. Intenta con más luz.");
                    }
                } catch(e) {
                    alert("Error procesando imagen.");
                } finally {
                    btn.innerHTML = "📷 Escanear Cupón de Papel";
                    btn.disabled = false;
                }
            };
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ==============================================================================
# ENDPOINTS REST
# ==============================================================================
@app.post("/scan")
async def scan_cupon(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    temp = f"temp_{file.filename}"
    with open(temp, "wb") as f: shutil.copyfileobj(file.file, f)
    try:
        datos = cupones.extraer_datos_cupon(temp)
        if not datos: return {"ok": False}
        database.guardar_cupon_orm(datos, user_uid=user_id)
        return {"ok": True, "data": datos}
    finally:
        if os.path.exists(temp): os.remove(temp)

@app.get("/cupones")
async def listar_cupones(user_id: str = Depends(get_current_user)):
    return database.obtener_cupones_usuario(user_id)

@app.post("/cupones/{cupon_id}/toggle_used")
async def marcar_usado(cupon_id: int, user_id: str = Depends(get_current_user)):
    database.alternar_estado_usado(cupon_id, user_id)
    return {"ok": True}

@app.delete("/cupones/{cupon_id}")
async def eliminar_cupon(cupon_id: int, user_id: str = Depends(get_current_user)):
    database.borrar_cupon(cupon_id, user_id)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)