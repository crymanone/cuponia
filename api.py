import shutil
import os
import json
from datetime import datetime
from collections import Counter

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

import firebase_admin
from firebase_admin import credentials, auth

import cupones      
import database     

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
            print("✅ [BOOT] Firebase Security CupónIA: ACTIVE")
        elif os.path.exists("firebase_credentials.json"):
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"⚠️ [BOOT] Error Firebase: {e}")

app = FastAPI(title="CupónIA Enterprise - Smart Coupon & Shopping List")
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
        "name": "CupónIA", "short_name": "CupónIA", "start_url": "/", "display": "standalone",
        "background_color": "#004d40", "theme_color": "#004d40",
        "icons":[{"src": "/cuponia_icon.png", "sizes": "512x512", "type": "image/png"}]
    })

@app.get("/cuponia_icon.png")
async def get_icon():
    if os.path.exists("cuponia_icon.png"): return FileResponse("cuponia_icon.png")
    return JSONResponse(status_code=404, content={"error": "Icono no encontrado"})

@app.get("/favicon.ico")
async def get_favicon():
    if os.path.exists("favicon.ico"): return FileResponse("favicon.ico")
    if os.path.exists("cuponia_icon.png"): return FileResponse("cuponia_icon.png")
    return JSONResponse(status_code=404, content={"error": "Icono no encontrado"})

@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy():
    return """
    <html><body>
    <h1>Política de Privacidad de CupónIA</h1>
    <p>CupónIA es una aplicación desarrollada por Juan Carlos Roade Martínez. Solo usamos la cámara y el micrófono para escanear tus cupones y dictar tu lista de la compra de forma privada y segura.</p>
    </body></html>
    """

# ==============================================================================
# FRONTEND INTERACTIVO (PWA CON CÁMARA 100% ADAPTABLE)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    html_content = r"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <title>CupónIA - Cartera y Lista de la Compra</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no, viewport-fit=cover">
        <link rel="manifest" href="/manifest.json">
        <link rel="icon" type="image/png" href="/cuponia_icon.png">
        <meta name="theme-color" content="#004d40">
        
        <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.5/dist/JsBarcode.all.min.js"></script>

        <style>
            :root { --primary: #004d40; --primary-light: #00796b; --accent: #ff6f00; --bg: #f4f6f8; --card: #ffffff; }
            body { font-family: 'Segoe UI', Roboto, sans-serif; background: var(--bg); margin: 0; color: #263238; display: flex; justify-content: center; min-height: 100vh; padding-bottom: 50px; }
            .app-container { width: 100%; max-width: 600px; padding: 15px; display: none; position: relative; }
            
            #loginScreen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; width: 100%; text-align: center; }
            .login-btn { background: white; color: #444; border: 1px solid #ddd; padding: 15px 30px; border-radius: 50px; font-weight: bold; font-size: 16px; display: flex; align-items: center; gap: 10px; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
            
            #user-info { position: absolute; top: 15px; right: 15px; z-index: 100; display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,0.95); padding: 5px 15px; border-radius: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); backdrop-filter: blur(5px); }
            .user-name { font-size: 13px; font-weight: 600; color: #37474f; }
            .logout-btn { background: #ff5252; color: white; border: none; padding: 6px 12px; border-radius: 20px; font-size: 11px; font-weight: bold; cursor: pointer; }
            
            header { text-align: center; margin-top: 50px; margin-bottom: 20px; }
            h1 { margin: 0; color: var(--primary); font-size: 34px; letter-spacing: -1px; font-weight: 900; }
            .tagline { color: #546e7a; font-size: 13px; margin-top: 5px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
            
            .savings-card { background: linear-gradient(135deg, #004d40, #00796b); color: white; padding: 20px; border-radius: 20px; text-align: center; box-shadow: 0 10px 25px rgba(0,77,64,0.3); margin-bottom: 20px; }
            .savings-amount { font-size: 36px; font-weight: 900; margin: 5px 0; color: #a7ffeb; }
            
            .card { background: white; padding: 20px; border-radius: 20px; box-shadow: 0 5px 20px rgba(0,0,0,0.04); margin-bottom: 20px; }
            h3 { margin-top: 0; color: var(--primary); font-size: 17px; display: flex; align-items: center; gap: 8px; font-weight: 800; }
            
            .btn { width: 100%; padding: 15px; border: none; border-radius: 14px; font-size: 15px; font-weight: 700; color: white; cursor: pointer; transition: 0.2s; box-sizing: border-box; text-align: center; }
            .btn-green { background: linear-gradient(135deg, #00796b, #004d40); box-shadow: 0 4px 12px rgba(0,77,64,0.3); }
            .btn-orange { background: linear-gradient(135deg, #ff6f00, #ffa000); box-shadow: 0 4px 12px rgba(255,111,0,0.3); }
            
            .filters-container { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 15px; scrollbar-width: none; }
            .chip { background: #e0f2f1; color: #004d40; padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap; border: 1px solid #b2dfdb; }
            .chip.active { background: var(--primary); color: white; border-color: var(--primary); }

            .coupon-item { background: white; border-radius: 16px; border: 1px solid #e0e0e0; margin-bottom: 15px; padding: 16px; position: relative; overflow: hidden; display: flex; flex-direction: column; gap: 8px; }
            .coupon-badge-market { background: #e0f2f1; color: #00796b; padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 800; text-transform: uppercase; display: inline-block; }
            .coupon-title { font-size: 17px; font-weight: bold; color: #263238; margin: 4px 0; }
            .coupon-conditions { font-size: 12px; color: #78909c; }
            
            .tag-urgent { background: #ffebee; color: #c62828; font-weight: 800; font-size: 11px; padding: 4px 8px; border-radius: 6px; }
            .tag-ok { background: #e8f5e9; color: #2e7d32; font-weight: 800; font-size: 11px; padding: 4px 8px; border-radius: 6px; }
            .tag-expired { background: #eeeeee; color: #9e9e9e; text-decoration: line-through; font-size: 11px; padding: 4px 8px; border-radius: 6px; }
            
            /* Lista de la compra */
            .shopping-input-box { display: flex; gap: 8px; margin-bottom: 15px; align-items: center; }
            .shopping-input { flex: 1; padding: 14px 16px; border: 2px solid #b2dfdb; border-radius: 12px; font-size: 15px; outline: none; font-weight: 600; box-sizing: border-box; }
            .btn-mic { width: 50px; height: 50px; border-radius: 12px; background: var(--primary-light); color: white; border: none; font-size: 20px; cursor: pointer; display: flex; justify-content: center; align-items: center; transition: 0.2s; }
            .shopping-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 10px; border-bottom: 1px solid #f0f0f0; transition: 0.2s; }
            .shopping-item.checked span.product-name { text-decoration: line-through; color: #9e9e9e; }
            .badge-coupon-match { background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: bold; margin-left: 8px; display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
            
            .app-footer { margin-top: 40px; padding: 25px; background: var(--primary); color: white; text-align: center; border-radius: 16px; box-shadow: 0 10px 20px rgba(0,77,64,0.2); }
            .legal-text { font-size: 10px; margin-top: 10px; opacity: 0.7; line-height: 1.4; }

            #barcodeModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 3000; justify-content: center; align-items: center; }
            .barcode-box { background: white; padding: 25px 20px; border-radius: 20px; width: 90%; max-width: 360px; text-align: center; }
            
            /* --- NUEVOS ESTILOS CÁMARA ADAPTABLE (100dvh + Flexbox Seguro) --- */
            #cameraModal { 
                display: none; 
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100vh; 
                height: 100dvh; /* Altura dinámica que se adapta a las barras de Android */
                background: #000; 
                z-index: 2000; 
                flex-direction: column; 
                box-sizing: border-box;
                overflow: hidden;
            }
            .camera-header { 
                width: 100%; 
                padding: 12px 16px; 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                box-sizing: border-box; 
                color: white; 
                z-index: 10; 
                background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent);
                flex-shrink: 0;
            }
            .camera-viewport { 
                position: relative; 
                width: 100%; 
                flex: 1; 
                min-height: 0; /* Evita que el vídeo empuje la barra inferior fuera de pantalla */
                display: flex; 
                justify-content: center; 
                align-items: center; 
                overflow: hidden; 
            }
            #cameraVideo { 
                width: 100%; 
                height: 100%; 
                object-fit: cover; 
            }
            .camera-guide { 
                position: absolute; 
                width: 80%; 
                max-width: 320px; 
                height: 60%; 
                max-height: 380px; 
                border: 2px dashed #00e676; 
                border-radius: 20px; 
                box-shadow: 0 0 0 9999px rgba(0,0,0,0.5); 
                pointer-events: none; 
                display: flex;
                justify-content: center;
                align-items: flex-end;
                padding-bottom: 15px;
            }
            .camera-guide-text { 
                color: white; 
                font-size: 11px; 
                font-weight: bold; 
                background: rgba(0,0,0,0.7); 
                padding: 4px 12px; 
                border-radius: 20px; 
            }
            .camera-footer { 
                width: 100%; 
                padding: 15px 0 calc(15px + env(safe-area-inset-bottom, 10px)) 0; 
                background: rgba(0,0,0,0.85); 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                gap: 40px; 
                flex-shrink: 0; /* Prohíbe que el botón se salga de la pantalla */
                box-sizing: border-box;
            }
            .btn-shutter { 
                width: 70px; 
                height: 70px; 
                border-radius: 50%; 
                background: white; 
                border: 4px solid var(--primary); 
                box-shadow: 0 0 20px rgba(255,255,255,0.4); 
                cursor: pointer; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                transition: 0.1s; 
            }
            .btn-shutter:active { transform: scale(0.92); }
            .btn-shutter-inner { width: 52px; height: 52px; border-radius: 50%; background: var(--primary); }
            .btn-camera-action { 
                background: rgba(255,255,255,0.25); 
                border: none; 
                color: white; 
                border-radius: 50%; 
                width: 42px; 
                height: 42px; 
                font-size: 18px; 
                cursor: pointer; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
            }
        </style>
    </head>
    <body>
        
        <!-- PANTALLA LOGIN -->
        <div id="loginScreen">
            <img src="/cuponia_icon.png" width="110" style="border-radius:24px; box-shadow:0 10px 30px rgba(0,77,64,0.3); margin-bottom:15px;">
            <h1 style="color:#004d40; margin:0 0 5px 0;">CupónIA</h1>
            <p style="color:#666; margin-bottom:25px;">Tu Cartera Inteligente de Descuentos</p>
            <button class="login-btn" onclick="loginWithGoogle()">
                <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="20">
                <span>Acceder con Google</span>
            </button>
        </div>

        <!-- APP PRINCIPAL -->
        <div id="appScreen" class="app-container">
            <div id="user-info"></div>

            <header>
                <h1>CupónIA</h1>
                <div class="tagline">Ahorro Inteligente de Supermercado</div>
            </header>

            <!-- TARJETA AHORRO TOTAL -->
            <div class="savings-card">
                <div style="font-size:13px; font-weight:bold; text-transform:uppercase;">💰 Tu Ahorro Disponible</div>
                <div id="totalSavings" class="savings-amount">0.00 €</div>
                <div style="font-size:11px; opacity:0.8;">En cupones activos listos para canjear</div>
            </div>

            <!-- LISTA INTELIGENTE DE LA COMPRA -->
            <div class="card" style="border: 2px solid #b2dfdb;">
                <h3>📝 Lista de la Compra Inteligente</h3>
                <p style="font-size:12px; color:#666; margin-top:-5px; margin-bottom:15px;">Escribe o pulsa el micro para dictar productos. ¡Te avisaremos si tienes cupón!</p>
                
                <div class="shopping-input-box">
                    <input type="text" id="inputProducto" class="shopping-input" placeholder="Ej: Leche, Aceite, Detergente...">
                    <button id="btnMic" class="btn-mic" onclick="iniciarDictadoVoz()" title="Dictar por voz">🎙️</button>
                    <button class="btn btn-green" style="width:auto; padding:14px 18px;" onclick="agregarItemManual()">➕</button>
                </div>

                <div id="shoppingListContainer" style="margin-top:10px;">Cargando lista...</div>
                
                <div style="text-align:right; margin-top:15px;">
                    <span onclick="limpiarComprados()" style="font-size:12px; color:#c62828; cursor:pointer; font-weight:bold; text-decoration:underline;">🧹 Limpiar productos comprados</span>
                </div>
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

            <!-- FOOTER LEGAL CON AUTORÍA OFICIAL -->
            <div class="app-footer">
                <div style="font-weight:700; font-size:16px;">CupónIA © <span id="year"></span></div>
                <div style="margin-top:5px; font-weight:500;">Juan Carlos Roade Martínez</div>
                <div class="legal-text">
                    Aplicación independiente desarrollada como utilidad personal de ahorro familiar.<br>
                    No afiliada ni respaldada por Carrefour, Dia, Mercadona, Lidl, Eroski ni ninguna cadena de supermercados.<br>
                    Todos los derechos reservados.
                </div>
            </div>
        </div>

        <!-- MODAL CÓDIGO DE BARRAS -->
        <div id="barcodeModal">
            <div class="barcode-box">
                <h3 id="modalMarket" style="margin:0; justify-content:center; text-transform:uppercase; color:#004d40;">Carrefour</h3>
                <p id="modalTitle" style="font-weight:bold; font-size:15px; margin:5px 0 15px 0;">3€ en Pescadería</p>
                
                <div style="background:white; padding:10px; border-radius:10px; border:1px solid #ddd;">
                    <svg id="barcodeSvg" style="width:100%;"></svg>
                </div>

                <p style="font-size:11px; color:#666; margin:10px 0;">Acerca la pantalla al lector de caja</p>
                <button class="btn btn-green" style="margin-bottom:8px;" onclick="marcarCanjeadoModal()">✅ Ya lo he usado</button>
                <button class="btn" style="background:#eee; color:#333;" onclick="cerrarBarcode()">Cerrar</button>
            </div>
        </div>

        <!-- MODAL CÁMARA IN-APP (100% Adaptable) -->
        <div id="cameraModal">
            <div class="camera-header">
                <button id="btnTorch" class="btn-camera-action" onclick="toggleTorch()" title="Encender Linterna">🔦</button>
                <span style="font-weight:bold; font-size:14px;">📸 Encuadra el Cupón</span>
                <button class="btn-camera-action" onclick="cerrarCamara()">✕</button>
            </div>
            <div class="camera-viewport">
                <video id="cameraVideo" autoplay playsinline></video>
                <div class="camera-guide">
                    <span class="camera-guide-text">Alinea el cupón aquí</span>
                </div>
            </div>
            <div class="camera-footer">
                <button id="btnCapturar" class="btn-shutter" onclick="capturarFoto()">
                    <div class="btn-shutter-inner"></div>
                </button>
            </div>
        </div>
        <canvas id="cameraCanvas" style="display:none;"></canvas>

        <!-- JAVASCRIPT CORE -->
        <script type="module">
            import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
            import { getAuth, signInWithPopup, GoogleAuthProvider, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

            const app = initializeApp({ apiKey: "AIzaSyCFB2fuuwpP-YJNzF9oFebutaK4ZHoM9tc", authDomain: "lotia-f4e4f.firebaseapp.com", projectId: "lotia-f4e4f" });
            const auth = getAuth();
            const provider = new GoogleAuthProvider();

            window.userToken = null;
            window.allCoupons = [];
            window.shoppingList = [];
            window.selectedMarket = 'todos';
            window.currentCouponIdModal = null;

            document.getElementById('year').innerText = new Date().getFullYear();

            onAuthStateChanged(auth, async (u) => {
                if (u) {
                    window.userToken = await u.getIdToken();
                    document.getElementById('loginScreen').style.display = 'none';
                    document.getElementById('appScreen').style.display = 'block';
                    
                    const n = u.displayName ? u.displayName.split(' ')[0] : 'Usuario';
                    document.getElementById('user-info').innerHTML = `<span class="user-name">Hola, ${n}</span> <button class="logout-btn" onclick="window.logout()">🚪 Salir</button>`;
                    
                    await window.loadCoupons();
                    await window.loadShoppingList();
                } else {
                    document.getElementById('loginScreen').style.display = 'flex';
                    document.getElementById('appScreen').style.display = 'none';
                }
            });

            window.loginWithGoogle = () => signInWithPopup(auth, provider).catch(e => alert(e.message));
            window.logout = () => signOut(auth).then(() => location.reload());

            async function authFetch(url, opts = {}) {
                if (!window.userToken) return alert("Sesión expirada");
                opts.headers = opts.headers || {};
                opts.headers['Authorization'] = 'Bearer ' + window.userToken;
                return fetch(url, opts);
            }

            // LISTA DE LA COMPRA INTELIGENTE
            window.loadShoppingList = async () => {
                try {
                    const res = await authFetch('/lista');
                    window.shoppingList = await res.json();
                    window.renderShoppingList();
                } catch(e) {}
            };

            function encontrarCuponMatch(nombreProducto) {
                if (!window.allCoupons || !nombreProducto) return null;
                const pLower = nombreProducto.toLowerCase().trim();
                const palabras = pLower.split(/\s+/).filter(w => w.length > 2);

                for (const c of window.allCoupons) {
                    if (c.is_used) continue;
                    const textoCupón = `${c.titulo} ${c.condiciones} ${c.supermercado}`.toLowerCase();
                    if (textoCupón.includes(pLower)) return c;
                    for (const palabra of palabras) {
                        if (textoCupón.includes(palabra)) return c;
                    }
                }
                return null;
            }

            window.renderShoppingList = () => {
                const container = document.getElementById('shoppingListContainer');
                if (window.shoppingList.length === 0) {
                    container.innerHTML = "<div style='text-align:center; padding:15px; color:#90a4ae; font-size:13px;'>Tu lista está vacía. ¡Prueba a dictar un producto con el micro!</div>";
                    return;
                }

                let html = "";
                window.shoppingList.forEach(item => {
                    const cuponMatch = encontrarCuponMatch(item.producto);
                    let badgeHtml = "";

                    if (cuponMatch && !item.is_checked) {
                        badgeHtml = `<span class="badge-coupon-match" onclick="mostrarBarcode(${cuponMatch.id}, '${cuponMatch.supermercado}', '${cuponMatch.titulo}', '${cuponMatch.codigo_barras}')">🏷️ ¡${cuponMatch.supermercado}: ${cuponMatch.titulo}!</span>`;
                    }

                    html += `
                    <div class="shopping-item ${item.is_checked ? 'checked' : ''}">
                        <div style="display:flex; align-items:center; flex:1;">
                            <input type="checkbox" style="width:18px; height:18px; margin-right:10px; cursor:pointer;" ${item.is_checked ? 'checked' : ''} onchange="toggleCheckItem(${item.id})">
                            <span class="product-name" style="font-size:15px; font-weight:600;">${item.producto}</span>
                            ${badgeHtml}
                        </div>
                        <button style="background:none; border:none; font-size:16px; cursor:pointer; opacity:0.6;" onclick="borrarItem(${item.id})">🗑️</button>
                    </div>`;
                });

                container.innerHTML = html;
            };

            window.agregarItemManual = async () => {
                const inp = document.getElementById('inputProducto');
                const val = inp.value.trim();
                if (!val) return;

                await authFetch('/lista', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ producto: val })
                });

                inp.value = "";
                await window.loadShoppingList();
            };

            window.toggleCheckItem = async (id) => {
                await authFetch(`/lista/${id}/toggle`, { method: 'POST' });
                await window.loadShoppingList();
            };

            window.borrarItem = async (id) => {
                await authFetch(`/lista/${id}`, { method: 'DELETE' });
                await window.loadShoppingList();
            };

            window.limpiarComprados = async () => {
                await authFetch('/lista/limpiar_completados', { method: 'DELETE' });
                await window.loadShoppingList();
            };

            // DICTADO POR VOZ
            let recognition = null;
            let isListening = false;

            window.iniciarDictadoVoz = () => {
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (!SpeechRecognition) return alert("Tu móvil no soporta dictado por voz. Usa el teclado.");

                const micBtn = document.getElementById('btnMic');
                if (isListening) {
                    if (recognition) recognition.stop();
                    return;
                }

                recognition = new SpeechRecognition();
                recognition.lang = 'es-ES';
                recognition.continuous = false;
                recognition.interimResults = false;

                recognition.onstart = () => {
                    isListening = true;
                    micBtn.style.background = "#d32f2f";
                    micBtn.innerText = "🔴";
                };

                recognition.onresult = async (event) => {
                    const textoDictado = event.results[0][0].transcript;
                    document.getElementById('inputProducto').value = textoDictado;
                    await window.agregarItemManual();
                };

                recognition.onerror = (e) => console.log("Error voz:", e);

                recognition.onend = () => {
                    isListening = false;
                    micBtn.style.background = "var(--primary-light)";
                    micBtn.innerText = "🎙️";
                };

                recognition.start();
            };

            // LÓGICA DE CUPONES
            window.loadCoupons = async () => {
                try {
                    const res = await authFetch('/cupones');
                    window.allCoupons = await res.json();
                    window.renderCoupons();
                    if (window.shoppingList.length > 0) window.renderShoppingList();
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
                    if (c.is_used) return false;
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

                    if (!c.is_used && !isExpired) totalSavings += c.importe || 0;

                    html += `
                    <div class="coupon-item">
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

            window.mostrarBarcode = (id, market, title, code) => {
                window.currentCouponIdModal = id;
                document.getElementById('modalMarket').innerText = market;
                document.getElementById('modalTitle').innerText = title;
                document.getElementById('barcodeModal').style.display = 'flex';

                try {
                    JsBarcode("#barcodeSvg", code, {
                        format: "CODE128", width: 2.5, height: 80, displayValue: true, fontSize: 16
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
                if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
                window.loadCoupons();
            };

            window.borrarCupon = async (id) => {
                if (confirm("¿Eliminar este cupón de tu cartera?")) {
                    await authFetch(`/cupones/${id}`, {method:'DELETE'});
                    window.loadCoupons();
                }
            };

            // CÁMARA IN-APP WEBRTC ADAPTABLE
            let cameraStream = null;
            let torchActive = false;

            window.abrirCamara = async () => {
                const modal = document.getElementById('cameraModal');
                const video = document.getElementById('cameraVideo');
                modal.style.display = 'flex';
                torchActive = false;
                document.getElementById('btnTorch').style.background = "rgba(255,255,255,0.25)";

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
                const modal = document.getElementById('cameraModal');
                const video = document.getElementById('cameraVideo');
                if (cameraStream) {
                    cameraStream.getTracks().forEach(track => track.stop());
                    cameraStream = null;
                }
                if (video) video.srcObject = null;
                modal.style.display = 'none';
                torchActive = false;
            };

            window.toggleTorch = async () => {
                if (!cameraStream) return;
                const track = cameraStream.getVideoTracks()[0];
                if (!track) return;
                const capabilities = track.getCapabilities ? track.getCapabilities() : {};
                if (!capabilities.torch) return alert("Flash no disponible");
                torchActive = !torchActive;
                await track.applyConstraints({ advanced: [{ torch: torchActive }] });
                document.getElementById('btnTorch').style.background = torchActive ? "#ffd54f" : "rgba(255,255,255,0.25)";
            };

            window.capturarFoto = () => {
                const video = document.getElementById('cameraVideo');
                const canvas = document.getElementById('cameraCanvas');
                const btn = document.getElementById('btnCapturar');
                
                if (!video || !canvas || !cameraStream) return;

                btn.disabled = true;
                btn.style.opacity = "0.5";

                canvas.width = video.videoWidth || 1280;
                canvas.height = video.videoHeight || 720;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                canvas.toBlob(async (blob) => {
                    window.cerrarCamara();
                    btn.disabled = false;
                    btn.style.opacity = "1";

                    if (!blob) return alert("Error al capturar la imagen.");

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

@app.get("/lista")
async def listar_items(user_id: str = Depends(get_current_user)):
    return database.obtener_lista_usuario(user_id)

@app.post("/lista")
async def agregar_item(data: dict = Body(...), user_id: str = Depends(get_current_user)):
    database.guardar_item_lista(data.get("producto", ""), user_id)
    return {"ok": True}

@app.post("/lista/{item_id}/toggle")
async def check_item(item_id: int, user_id: str = Depends(get_current_user)):
    database.alternar_check_item(item_id, user_id)
    return {"ok": True}

@app.delete("/lista/{item_id}")
async def eliminar_item(item_id: int, user_id: str = Depends(get_current_user)):
    database.borrar_item_lista(item_id, user_id)
    return {"ok": True}

@app.delete("/lista/limpiar_completados")
async def limpiar_items_completados(user_id: str = Depends(get_current_user)):
    database.limpiar_lista_completados(user_id)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)