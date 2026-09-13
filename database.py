import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cuponia.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS ---
class Cupon(Base):
    __tablename__ = "cupones"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, default="anonimo")
    supermercado = Column(String, default="Supermercado") 
    titulo_descuento = Column(String)                     
    importe_descuento = Column(Float, default=0.0)        
    condiciones = Column(String, nullable=True)           
    fecha_caducidad = Column(String)                      
    codigo_barras = Column(String, nullable=True)         
    is_used = Column(Boolean, default=False)              
    created_at = Column(DateTime, default=datetime.utcnow)

class ItemLista(Base):
    __tablename__ = "items_lista"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, default="anonimo")
    producto = Column(String)                             # Ej: "Aceite de oliva"
    is_checked = Column(Boolean, default=False)           # Tachado en el carrito
    created_at = Column(DateTime, default=datetime.utcnow)

# --- INICIALIZACIÓN ---
def inicializar_db():
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE cupones ADD COLUMN IF NOT EXISTS importe_descuento FLOAT DEFAULT 0.0;"))
            conn.commit()
    except Exception: pass

# --- FUNCIONES DE CUPONES ---
def guardar_cupon_orm(datos_json, user_uid="anonimo"):
    db = SessionLocal()
    try:
        importe = 0.0
        try:
            imp_str = str(datos_json.get("importe_descuento", "0")).replace("€", "").replace(",", ".").strip()
            importe = float(imp_str)
        except Exception:
            importe = 0.0

        nuevo = Cupon(
            user_id=user_uid,
            supermercado=datos_json.get("supermercado", "Supermercado").capitalize(),
            titulo_descuento=datos_json.get("titulo_descuento", "Descuento en producto"),
            importe_descuento=importe,
            condiciones=datos_json.get("condiciones", ""),
            fecha_caducidad=datos_json.get("fecha_caducidad", "Sin fecha"),
            codigo_barras=str(datos_json.get("codigo_barras", "")).strip(),
            is_used=False
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        return nuevo.id
    except Exception as e:
        db.rollback()
        return None
    finally:
        db.close()

def obtener_cupones_usuario(user_uid):
    db = SessionLocal()
    cupones = db.query(Cupon).filter(Cupon.user_id == user_uid).order_by(Cupon.id.desc()).all()
    resultado =[]
    for c in cupones:
        resultado.append({
            "id": c.id, "supermercado": c.supermercado, "titulo": c.titulo_descuento,
            "importe": c.importe_descuento, "condiciones": c.condiciones,
            "fecha_caducidad": c.fecha_caducidad, "codigo_barras": c.codigo_barras,
            "is_used": c.is_used
        })
    db.close()
    return resultado

def alternar_estado_usado(cupon_id, user_uid):
    db = SessionLocal()
    try:
        c = db.query(Cupon).filter(Cupon.id == cupon_id, Cupon.user_id == user_uid).first()
        if c:
            c.is_used = not c.is_used
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

def borrar_cupon(cupon_id, user_uid):
    db = SessionLocal()
    try:
        c = db.query(Cupon).filter(Cupon.id == cupon_id, Cupon.user_id == user_uid).first()
        if c:
            db.delete(c)
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

# --- NUEVAS FUNCIONES DE LA LISTA DE LA COMPRA ---
def guardar_item_lista(producto, user_uid):
    db = SessionLocal()
    try:
        nuevo = ItemLista(user_id=user_uid, producto=producto.strip(), is_checked=False)
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        return nuevo.id
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()

def obtener_lista_usuario(user_uid):
    db = SessionLocal()
    items = db.query(ItemLista).filter(ItemLista.user_id == user_uid).order_by(ItemLista.id.asc()).all()
    resultado = [{"id": i.id, "producto": i.producto, "is_checked": i.is_checked} for i in items]
    db.close()
    return resultado

def alternar_check_item(item_id, user_uid):
    db = SessionLocal()
    try:
        item = db.query(ItemLista).filter(ItemLista.id == item_id, ItemLista.user_id == user_uid).first()
        if item:
            item.is_checked = not item.is_checked
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

def borrar_item_lista(item_id, user_uid):
    db = SessionLocal()
    try:
        item = db.query(ItemLista).filter(ItemLista.id == item_id, ItemLista.user_id == user_uid).first()
        if item:
            db.delete(item)
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

def limpiar_lista_completados(user_uid):
    db = SessionLocal()
    try:
        db.query(ItemLista).filter(ItemLista.user_id == user_uid, ItemLista.is_checked == True).delete()
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()