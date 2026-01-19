import os
import json
import unicodedata
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse

# ==========================================
# 1. CONFIGURACIÓN Y RUTAS
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Rutas Específicas
DF_PATH = DATA_DIR / "df_final_f2.csv"
WORLD_PATH = DATA_DIR / "world_geometries.geojson"
THAI_DATA_PATH = DATA_DIR / "thailand_subdistrict_cases.csv"
THAI_GEO_PATH = DATA_DIR / "bangkok_admin3.geojson"
CASOS_ARG_PATH = DATA_DIR / "casos_ARG.csv"
SHP_ARG_PATH = DATA_DIR / "geo_argentina" / "pxdptodatosok.shp"
# Ruta Brasil (Shapefile absoluto y CSV relativo a data)
# CAMBIO CORRECTO:
# SHP_BRA_PATH = DATA_DIR / "BRA" / "BR_Municipios_2024" / "BR_Municipios_2024.shp"
SHP_BRA_PATH = "zip://" + str(DATA_DIR / "BRA" / "BR_Municipios_2024" / "BR_Municipios_2024.zip")
CSV_BRA_PATH = DATA_DIR / "casos_brasil_resumen.csv"

# ==========================================
# 2. INICIALIZAR APP
# ==========================================
app = FastAPI(title="DengueViewer API")


origins = [
    "http://localhost:5173",          # Tu Vue corriendo en local
    "http://127.0.0.1:5173",
    "https://plataforma-dengue.onrender.com", # Tu URL real de Render
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # <-- Usamos la lista en lugar de "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 3. CARGA DE DATOS MUNDIALES (Al inicio)
# ==========================================
print("--- Cargando Datos Mundiales ---")
try:
    df = pd.read_csv(DF_PATH)
    world = gpd.read_file(WORLD_PATH)

    if "area_km2" not in world.columns:
        world_aea = world.to_crs("EPSG:6933")
        world["area_km2"] = world_aea.area / 1_000_000

    world = world[["iso3", "geometry", "area_km2"]]
    gdf = df.merge(world, on="iso3", how="left")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.dropna(subset=["geometry"])

    gdf["year_week"] = (
        gdf["Year"].astype(int).astype(str)
        + "-W"
        + gdf["Epi. Week (a)"].astype(int).astype(str).str.zfill(2)
    )
    weeks_list = sorted(gdf["year_week"].unique())
    print(f"Mundo cargado: {len(weeks_list)} semanas.")
except Exception as e:
    print(f"Error cargando mundo: {e}")
    weeks_list = []
    gdf = gpd.GeoDataFrame()

# ==========================================
# 4. CARGA DE DATOS TAILANDIA
# ==========================================
print("--- Cargando Datos Tailandia ---")
try:
    df_thai = pd.read_csv(THAI_DATA_PATH)
    df_thai['ID_MAPA'] = df_thai['ID_MAPA'].astype(str)
    
    gdf_thai_geo = gpd.read_file(THAI_GEO_PATH)
    
    # Detectar columnas
    col_prov = 'ADM1_PCODE' if 'ADM1_PCODE' in gdf_thai_geo.columns else 'adm1_pcode'
    col_subdist = 'ADM3_PCODE' if 'ADM3_PCODE' in gdf_thai_geo.columns else 'adm3_pcode'
    
    # Filtrar Bangkok (TH10)
    gdf_thai_geo = gdf_thai_geo[gdf_thai_geo[col_prov] == 'TH10'].copy()
    
    # Merge
    gdf_thai = gdf_thai_geo.merge(df_thai, left_on=col_subdist, right_on='ID_MAPA', how='left')
    gdf_thai['Cases'] = gdf_thai['Cases'].fillna(0)
    
    # Densidad
    if 'area_sqkm' in gdf_thai.columns:
         gdf_thai['density'] = gdf_thai['Cases'] / gdf_thai['area_sqkm']
    elif 'Shape_Area' in gdf_thai.columns:
         gdf_thai['density'] = gdf_thai['Cases'] / (gdf_thai['Shape_Area'] / 1_000_000)
    else:
         gdf_thai['density'] = 0
         
    print(f"Tailandia OK: {len(gdf_thai)} zonas.")
except Exception as e:
    print(f"Error Tailandia: {e}")
    gdf_thai = gpd.GeoDataFrame()

# ==========================================
# 5. CARGA DE DATOS ARGENTINA (Helpers)
# ==========================================
gdf_arg_cache = None

def norm_txt(x):
    if pd.isna(x): return ""
    x = str(x).strip().upper()
    x = "".join(c for c in unicodedata.normalize("NFKD", x) if not unicodedata.combining(c))
    return " ".join(x.split())

PROV_MAP = {"CABA": "CIUDAD AUTONOMA DE BUENOS AIRES", "CAPITAL FEDERAL": "CIUDAD AUTONOMA DE BUENOS AIRES"}

# ============================================================
# ARGENTINA DATA LOADER (NIVEL DEPARTAMENTOS)
# ============================================================

# ============================================================
# ARGENTINA DATA LOADER (POR NOMBRE DE DEPARTAMENTO)
# ============================================================

gdf_arg_cache = None

# Función auxiliar para limpiar texto (Quitar tildes, mayúsculas, espacios)
def clean_text(text):
    if pd.isna(text): return ""
    # Convertir a texto, mayúsculas y quitar espacios extremos
    text = str(text).upper().strip()
    # Quitar tildes (Á -> A, ñ -> n)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return text

def load_arg_data():
    global gdf_arg_cache
    if gdf_arg_cache is not None:
        return gdf_arg_cache

    print("--- Cargando datos de Argentina (Merge por Nombres) ---")

    try:
        # 1. CARGAR SHAPEFILE
        if not os.path.exists(SHP_ARG_PATH):
            print("ERROR: No existe SHP Argentina")
            return pd.DataFrame()
            
        gdf = gpd.read_file(SHP_ARG_PATH)
        
        # Simplificar geometría para velocidad
        gdf["geometry"] = gdf["geometry"].simplify(0.01)

        # --- PREPARAR LLAVE EN EL MAPA ---
        # Buscamos columnas de nombres. Usualmente: 'departamen' (o 'nam') y 'provincia'
        col_dept_shp = next((c for c in gdf.columns if c.lower() in ['departamen', 'nam', 'nombre']), None)
        col_prov_shp = next((c for c in gdf.columns if c.lower() in ['provincia', 'prov']), None)
        
        if not col_dept_shp:
            print(f"!!! ERROR SHP: No encuentro columna de nombre de departamento. Columnas: {gdf.columns}")
            return pd.DataFrame()

        print(f"Usando columnas SHP: Depto='{col_dept_shp}', Prov='{col_prov_shp}'")

        # Creamos llave única: PROVINCIA_DEPARTAMENTO (Ej: "BUENOS AIRES_AVELLANEDA")
        # Esto evita confundir "San Martín" de Buenos Aires con "San Martín" de Mendoza.
        gdf['key_join'] = (
            gdf[col_prov_shp].apply(clean_text) + "_" + 
            gdf[col_dept_shp].apply(clean_text)
        )

        # 2. CARGAR CSV
        print(f"Leyendo CSV desde: {CASOS_ARG_PATH}")
        df_casos = pd.read_csv(CASOS_ARG_PATH, sep=None, engine='python')
        df_casos.columns = df_casos.columns.str.strip().str.upper() # Todo mayúsculas

        # Normalizar columnas
        if "AÑO" in df_casos.columns: df_casos.rename(columns={"AÑO": "ANIO"}, inplace=True)
        if "ISO_WEEK" in df_casos.columns: df_casos.rename(columns={"ISO_WEEK": "SEPI"}, inplace=True)

        # --- PREPARAR LLAVE EN EL CSV ---
        # Usamos tus columnas: PROVINCIA y DEPARTAMENTO
        if 'PROVINCIA' not in df_casos.columns or 'DEPARTAMENTO' not in df_casos.columns:
            print("!!! ERROR CSV: Faltan columnas 'PROVINCIA' o 'DEPARTAMENTO'")
            return pd.DataFrame()

        df_casos['key_join'] = (
            df_casos['PROVINCIA'].apply(clean_text) + "_" + 
            df_casos['DEPARTAMENTO'].apply(clean_text)
        )

        # 3. AGRUPAR
        print("Agrupando datos...")
        df_grouped = df_casos.groupby(["key_join", "ANIO", "SEPI"], as_index=False)["CONFIRMADO"].sum()

        df_grouped["year_week"] = (
            df_grouped["ANIO"].astype(str) + "-" + 
            df_grouped["SEPI"].astype(str).str.zfill(2)
        )

        # 4. MERGE (Unir por la llave de texto creada)
        # Left merge para mantener el mapa completo
        merged = gdf.merge(df_grouped, on="key_join", how="left")
        merged["CONFIRMADO"] = merged["CONFIRMADO"].fillna(0)
        
        # Filtramos para devolver solo geometrías con datos temporales asociados
        # (Ojo: Esto ocultará departamentos que nunca tuvieron casos en el CSV. 
        #  Si quieres ver el mapa gris de fondo, avísame para cambiar la estrategia)
        gdf_arg_cache = merged[merged["year_week"].notna()]
        
        # Diagnóstico
        print(f"Registros finales: {len(gdf_arg_cache)}")
        print(f"Ejemplo llave mapa: {gdf['key_join'].iloc[0]}")
        print(f"Ejemplo llave CSV:  {df_grouped['key_join'].iloc[0]}")

        return gdf_arg_cache

    except Exception as e:
        print(f"Error Argentina: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
# ==========================================
# 6. ENDPOINTS DE LA API
# ==========================================

# --- MUNDO ---
@app.get("/api/weeks")
def get_weeks():
    return weeks_list

@app.get("/api/cases/{year_week}")
def get_cases(year_week: str):
    subset = gdf[gdf["year_week"] == year_week]
    data = []
    for _, row in subset.iterrows():
        cases = float(row.get("Casos_Nuevos", 0) or 0)
        area = float(row.get("area_km2", 0) or 0)
        data.append({
            "country": row["Country"],
            "cases": cases,
            "incidence": float(row.get("Inc_Nueva", 0) or 0),
            "area": area,
            "density": cases / area if area > 0 else 0.0,
            "geometry": mapping(row["geometry"]),
        })
    return {"week": year_week, "data": data}

# --- TAILANDIA ---
@app.get("/api/thailand/weeks")
def get_thai_weeks():
    if gdf_thai.empty: return []
    return sorted(gdf_thai["year_week"].dropna().unique().tolist())

@app.get("/api/thailand/cases/{year_week}")
def get_thai_cases(year_week: str):
    if gdf_thai.empty: return {"week": year_week, "data": []}
    subset = gdf_thai[gdf_thai["year_week"] == year_week]
    data = []
    for _, row in subset.iterrows():
        if pd.isna(row.geometry): continue
        data.append({
            "district": row.get("Subdistrict (English)", row.get("adm3_name", "Unknown")),
            "district_id": str(row.get("ID_MAPA")),
            "cases": float(row.get("Cases", 0)),
            "density": float(row.get("density", 0)),
            "geometry": mapping(row["geometry"])
        })
    return {"week": year_week, "data": data}

# --- ARGENTINA ---
@app.get("/api/argentina/weeks")
def api_get_arg_weeks():
    df = load_arg_data()
    if df.empty: return []
    return sorted(df["year_week"].dropna().astype(str).unique().tolist())

@app.get("/api/argentina/data")
def api_get_arg_data(week: str):
    df = load_arg_data()
    if df.empty: return "{}"
    subset = df[df["year_week"] == week].copy()
    return json.loads(subset.to_json())
# ==========================================
# BRASIL (ACTUALIZADO CON FILTRO DE SEMANAS)
# ==========================================

# Variables globales para caché (para no leer el CSV gigante cada vez)
df_brasil_cache = None
gdf_brasil_geo_cache = None
def load_brasil_resources():
    global df_brasil_cache, gdf_brasil_geo_cache
    
    # ---------------------------------------------------------
    # 1. CARGAR GEOMETRÍA (SHAPEFILE)
    # ---------------------------------------------------------
    if gdf_brasil_geo_cache is None:
        if os.path.exists(SHP_BRA_PATH):
            print(">>> [Brasil] Cargando Shapefile...")
            gdf = gpd.read_file(SHP_BRA_PATH)
            
            if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
            
            gdf["geometry"] = gdf["geometry"].simplify(0.01)
            
            # --- BLINDAJE DE ID MAPA ---
            # Asumimos que la columna es CD_MUN. La convertimos a string de 6 chars.
            # Ej: 2504108 -> 250410
            if 'CD_MUN' in gdf.columns:
                gdf['id_join'] = gdf['CD_MUN'].astype(str).str.strip().str.slice(0, 6)
            else:
                print("!!! ERROR CRÍTICO: El Shapefile no tiene columna CD_MUN")
            
            gdf_brasil_geo_cache = gdf
            print(f">>> [Brasil] Shapefile OK. IDs ejemplo: {gdf['id_join'].head(3).tolist()}")
        else:
            print(f">>> [Brasil] ERROR: No existe el Shapefile en {SHP_BRA_PATH}")

    # ---------------------------------------------------------
    # 2. CARGAR DATOS CSV (CORRECCIÓN FECHAS Y CRUCE)
    # ---------------------------------------------------------
    if df_brasil_cache is None:
        if os.path.exists(CSV_BRA_PATH):
            print(f">>> [Brasil] Cargando CSV...")
            
            try:
                # Detectar separador automáticamente
                df = pd.read_csv(CSV_BRA_PATH, sep=None, engine='python')
                
                # Normalizar nombres de columnas (Fecha, ID, Casos)
                # Tomamos las 3 primeras sin importar cómo se llamen
                df = df.iloc[:, 0:3]
                df.columns = ['fecha_raw', 'id_mun', 'casos']
                
                # --- CORRECCIÓN FECHAS ---
                # Convertimos a fecha
                df['dt'] = pd.to_datetime(df['fecha_raw'], dayfirst=True, errors='coerce')
                
                # ELIMINAR FECHAS BASURA (1911, 2106, NaT)
                # Solo aceptamos datos desde el año 2000 al 2030
                df = df.dropna(subset=['dt'])
                df = df[df['dt'].dt.year.between(2000, 2030)]
                
                df['year_week'] = df['dt'].dt.strftime('%G-W%V')
                
                # --- CORRECCIÓN IDs CSV ---
                # Convertir a string, quitar decimales (.0), quitar espacios, cortar a 6 chars
                df['ID_MN_RESI'] = df['id_mun'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.slice(0, 6)
                
                # Agrupar (Sumar casos si hay duplicados)
                df_grouped = df.groupby(['year_week', 'ID_MN_RESI'])['casos'].sum().reset_index()
                
                df_brasil_cache = df_grouped
                
                # --- DIAGNÓSTICO DE CRUCE (LO MÁS IMPORTANTE) ---
                if gdf_brasil_geo_cache is not None:
                    ids_mapa = set(gdf_brasil_geo_cache['id_join'])
                    ids_csv = set(df_brasil_cache['ID_MN_RESI'])
                    coincidencias = ids_mapa.intersection(ids_csv)
                    
                    print(f"\n>>> [DIAGNÓSTICO CRUCE BRASIL]")
                    print(f"    IDs únicos en Mapa: {len(ids_mapa)}")
                    print(f"    IDs únicos en CSV:  {len(ids_csv)}")
                    print(f"    IDs EN COMÚN:       {len(coincidencias)} (Si esto es 0, el mapa saldrá vacío)")
                    print(f"    Ejemplo ID Mapa: '{list(ids_mapa)[0]}'")
                    print(f"    Ejemplo ID CSV:  '{list(ids_csv)[0]}'")
                    print(f"    Rango Fechas: {df['dt'].min()} a {df['dt'].max()}")
                
            except Exception as e:
                print(f">>> [Brasil] ERROR LEYENDO CSV: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(">>> [Brasil] ERROR: No hay archivo CSV")
@app.get("/api/brasil/weeks")
def get_brasil_weeks():
    """Devuelve la lista de semanas disponibles para el slider"""
    load_brasil_resources()
    if df_brasil_cache is not None:
        # Ordenamos las semanas únicas
        weeks = sorted(df_brasil_cache['year_week'].unique().tolist())
        return weeks
    return []

@app.get("/api/brasil")
async def get_brasil_data(week: str = None):
    """
    Devuelve el GeoJSON. 
    Si week es None -> Devuelve acumulado total (o última semana).
    Si week existe -> Filtra por esa semana.
    """
    try:
        load_brasil_resources()
        
        if gdf_brasil_geo_cache is None:
            return {"error": "Shapefile no cargado"}
        
        gdf = gdf_brasil_geo_cache.copy()

        # Filtrar datos
        if df_brasil_cache is not None:
            df_filtered = df_brasil_cache
            
            if week:
                print(f">>> [Brasil] Filtrando semana: {week}")
                df_filtered = df_brasil_cache[df_brasil_cache['year_week'] == week]
            
            # Si hay múltiples filas por municipio en esa semana (raro), sumamos
            df_grouped = df_filtered.groupby('ID_MN_RESI')['casos'].sum().reset_index()
            
            # Merge
            gdf = gdf.merge(df_grouped, left_on='id_join', right_on='ID_MN_RESI', how='left')
            gdf["casos"] = gdf["casos"].fillna(0)
        else:
            gdf["casos"] = 0

        # Limpieza
        gdf = gdf.dropna(subset=['geometry'])
        gdf['NM_MUN'] = gdf['NM_MUN'].fillna("Sin Nombre")
        
        gdf_clean = gdf[['NM_MUN', 'id_join', 'casos', 'geometry']]
        gdf_clean = gpd.GeoDataFrame(gdf_clean, geometry='geometry')
        
        # MODO PRUEBA: Si sigue muy lento, descomenta esto:
        # gdf_clean = gdf_clean.iloc[:200]

        return json.loads(gdf_clean.to_json(na='null', show_bbox=False))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
 # ============================================================
# TAILANDIA DATA LOADER (CASOS + POBLACIÓN + MAPA)
# ============================================================

import pandas as pd
import geopandas as gpd
import json
import os
from pathlib import Path

# --- RUTAS DE ARCHIVOS ---
# Ajusta los nombres si tus archivos se llaman diferente
THAI_SHP_PATH = DATA_DIR / "geo_thailand" / "province_dd.shp"
THAI_CASES_PATH = DATA_DIR / "DengueThailand_2003-2024_Monthly.xlsx"
THAI_POP_PATH = DATA_DIR / "population_thai.xlsx" # Asegúrate de que este sea el nombre correcto

# Variables globales para caché
gdf_thai_cache = None       # Guardará Mapa + Población
df_thai_data_cache = None   # Guardará Casos históricos

def load_thailand_resources():
    global gdf_thai_cache, df_thai_data_cache
    
    # ---------------------------------------------------------
    # 1. CARGAR MAPA Y POBLACIÓN (SE UNEN UNA SOLA VEZ)
    # ---------------------------------------------------------
    if gdf_thai_cache is None:
        print(">>> [Tailandia] Inicializando Mapa y Población...")
        
        # A) Cargar Shapefile
        if os.path.exists(THAI_SHP_PATH):
            try:
                gdf = gpd.read_file(THAI_SHP_PATH)
                if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
                    gdf = gdf.to_crs("EPSG:4326")
                gdf["geometry"] = gdf["geometry"].simplify(0.01)
                
                # Detectar columna de nombre en el mapa (PROV_NAME es lo común)
                col_mapa = 'PROV_NAME' if 'PROV_NAME' in gdf.columns else gdf.columns[1]
                gdf['name_join'] = gdf[col_mapa].astype(str).str.strip().str.upper()
                
                # B) Cargar Población
                if os.path.exists(THAI_POP_PATH):
                    print("   + Cruzando datos de población...")
                    # Leemos Excel o CSV según corresponda
                    if str(THAI_POP_PATH).endswith('.csv'):
                        df_pop = pd.read_csv(THAI_POP_PATH)
                    else:
                        df_pop = pd.read_excel(THAI_POP_PATH)

                    # Columna de nombre en población ('Name ' con espacio a veces)
                    col_pop = 'Name ' if 'Name ' in df_pop.columns else 'Name'
                    df_pop['name_join'] = df_pop[col_pop].astype(str).str.strip().str.upper()
                    
                    # CORRECCIONES POBLACIÓN -> MAPA
                    correcciones_pop = {
                        'BANGKOK': 'KRUNG THEP MAHA NAKHON (BANGKOK)',
                        'CHAI NAT': 'CHAINAT',
                        'BUENG KAN': 'NONG KHAI' # Fallback si el mapa es viejo
                    }
                    df_pop['name_join'] = df_pop['name_join'].replace(correcciones_pop)
                    
                    # Merge: Mapa + Población
                    gdf = gdf.merge(df_pop[['name_join', 'Population']], on='name_join', how='left')
                    gdf['Population'] = gdf['Population'].fillna(0) # Evitar NaNs
                    
                    # Diagnóstico
                    sin_pop = gdf[gdf['Population'] == 0]
                    if len(sin_pop) > 0:
                        print(f"   ⚠️ {len(sin_pop)} provincias sin población (se verán pero incidencia será 0).")
                else:
                    print("   ❌ No se encontró archivo de población. La incidencia será 0.")
                    gdf['Population'] = 0

                gdf_thai_cache = gdf
                print("   ✅ Mapa y Población listos.")

            except Exception as e:
                print(f"❌ Error cargando Mapa/Pob: {e}")
                return
        else:
            print(f"❌ No existe SHP en: {THAI_SHP_PATH}")
            return

    # ---------------------------------------------------------
    # 2. CARGAR CASOS (EXCEL)
    # ---------------------------------------------------------
    if df_thai_data_cache is None:
        if os.path.exists(THAI_CASES_PATH):
            print(">>> [Tailandia] Procesando Casos...")
            try:
                # Leer Excel (o CSV)
                if str(THAI_CASES_PATH).endswith('.csv'):
                    df = pd.read_csv(THAI_CASES_PATH)
                else:
                    df = pd.read_excel(THAI_CASES_PATH, engine='openpyxl')
                
                # Transformar de Ancho a Largo (Melt)
                df_melted = df.melt(id_vars=['Date'], var_name='province_raw', value_name='cases')
                
                # Limpieza Fechas y Casos
                df_melted['Date'] = pd.to_datetime(df_melted['Date'], errors='coerce')
                df_melted = df_melted.dropna(subset=['Date'])
                df_melted['date_str'] = df_melted['Date'].dt.strftime('%Y-%m-%d')
                df_melted['cases'] = pd.to_numeric(df_melted['cases'], errors='coerce').fillna(0)
                
                # Normalizar nombres
                df_melted['name_join'] = df_melted['province_raw'].astype(str).str.strip().str.upper()
                
                # CORRECCIONES CASOS -> MAPA (El Diccionario Definitivo)
                correcciones_cases = {
                    'AYUTTHAYA': 'PHRA NAKHON SI AYUTTHAYA',
                    'BANGKOK': 'KRUNG THEP MAHA NAKHON (BANGKOK)',
                    'CHAI NAT': 'CHAINAT',
                    'BUNGKAN': 'BUENG KAN', # O 'NONG KHAI' si el mapa es viejo
                    'BURI RAM': 'BURIRAM',
                    'CHON BURI': 'CHONBURI',
                    'LOP BURI': 'LOPBURI',
                    'NONG BUA LAM PHU': 'NONG BUA LAMPHU',
                    'PHANGNGA': 'PHANG NGA',
                    'PRACHIN BURI': 'PRACHINBURI',
                    'SI SA KET': 'SISAKET'
                }
                df_melted['name_join'] = df_melted['name_join'].replace(correcciones_cases)
                
                # Agrupar por si las correcciones generaron duplicados (ej: 2 zonas mapeadas a 1)
                df_thai_data_cache = df_melted.groupby(['date_str', 'name_join', 'province_raw'], as_index=False)['cases'].sum()
                print(f"   ✅ Casos cargados: {len(df_thai_data_cache)} registros.")

            except Exception as e:
                print(f"❌ Error procesando Casos: {e}")
                import traceback
                traceback.print_exc()

# --- ENDPOINTS API ---

@app.get("/api/thailand/dates")
def get_thai_dates():
    load_thailand_resources()
    if df_thai_data_cache is not None:
        return sorted(df_thai_data_cache['date_str'].unique().tolist())
    return []

@app.get("/api/thailand/data")
def get_thai_data(date: str):
    """
    Retorna GeoJSON con:
    - cases: Número total
    - incidence: (Casos / Población) * 100k
    - Population: Población total
    """
    load_thailand_resources()
    
    if gdf_thai_cache is None or df_thai_data_cache is None:
        return {"features": []}
        
    try:
        # 1. Filtrar casos por la fecha solicitada
        df_filtered = df_thai_data_cache[df_thai_data_cache['date_str'] == date]
        
        # 2. Merge: (Mapa + Población) LEFT JOIN (Casos)
        merged = gdf_thai_cache.merge(df_filtered, on='name_join', how='left')
        
        # 3. Limpieza de nulos
        merged['cases'] = merged['cases'].fillna(0)
        merged['province_display'] = merged['province_raw'].fillna(merged['name_join'])
        
        # 4. CÁLCULO DE INCIDENCIA
        # Fórmula: (Casos / Población) * 100,000
        merged['incidence'] = 0.0
        
        # Solo calculamos donde Población > 0 para evitar división por cero
        mask = merged['Population'] > 0
        merged.loc[mask, 'incidence'] = (merged.loc[mask, 'cases'] / merged.loc[mask, 'Population']) * 100000
        
        # Redondear a 2 decimales
        merged['incidence'] = merged['incidence'].round(2)
        
        # 5. Generar GeoJSON
        # Seleccionamos solo las columnas necesarias para enviar menos datos
        gdf_clean = merged[['province_display', 'cases', 'incidence', 'Population', 'geometry']]
        
        return json.loads(gdf_clean.to_json(na='null', show_bbox=False))
        
    except Exception as e:
        print(f"Error en endpoint Tailandia: {e}")
        return {"error": str(e)}
    

#### BORRAR EN CASO DE ERROR

# --- AGREGAR ESTAS LIBRERÍAS AL INICIO ---
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

# ... (Tus otras importaciones y variables globales) ...

# ============================================================
# MODELO ML ENGINE (Lógica del Notebook llevada a la API)
# ============================================================

model_cache = None # Guardará {model, df_test, metrics, features}

def get_thai_model_resources():
    global model_cache
    if model_cache is not None:
        return model_cache

    print(">>> [ML Engine] Entrenando modelo de Tailandia...")
    
    # 1. Reutilizamos la función de carga que ya tienes para obtener el DF limpio
    load_thailand_resources() # Asegura que df_thai_data_cache y clima estén cargados
    
    # Nota: Aquí asumimos que load_thailand_resources ya cargó y unió Casos + Clima + Vecinos.
    # Si tu función load_thailand_resources solo carga el raw, necesitamos replicar
    # la ingeniería de features (lags, log, etc) aquí. 
    # POR SIMPLICIDAD: Asumiré que copias el bloque de "Feature Engineering" aquí dentro.
    
    # --- REPLICAR INGENIERÍA DE FEATURES DEL NOTEBOOK ---
    # (Para no hacer el código gigante aquí, asegúrate de que df_thai_data_cache 
    # tenga las columnas 'change_t-1', 'temp_t-1', etc. Si no, añádelas aquí).
    
    # Supongamos que df_thai_data_cache ya tiene los merges básicos.
    # Recalculamos features rápido para asegurar:
    df = df_thai_data_cache.copy() # Usar el df global cargado previamente
    
    # Asegurar orden
    df['date'] = pd.to_datetime(df['date_str'])
    df = df.sort_values(['province_raw', 'date'])
    
    # Target y Features
    df['log_cases'] = np.log1p(df['cases'])
    df['y_change_t1'] = df.groupby('province_raw')['log_cases'].shift(-1) - df['log_cases']
    
    # Lags (Simplificado para producción)
    for l in [1, 2, 3]:
        df[f'change_t-{l}'] = df.groupby('province_raw')['log_cases'].shift(l) - df.groupby('province_raw')['log_cases'].shift(l+1)
        # Asumiendo que ya tienes clima y vecinos unidos en df_thai_data_cache
        # Si no, deberías hacer los merges aquí igual que en el notebook.
    
    df['month'] = df['date'].dt.month
    df_model = df.dropna().copy()
    
    # --- ENTRENAMIENTO ---
    train = df_model[df_model['date'].dt.year < 2024]
    test = df_model[df_model['date'].dt.year == 2024]
    
    features = [c for c in df_model.columns if 'change_t-' in c or c == 'month']
    # (Añade temp/rain/vecinos a 'features' si están en tu df global)
    
    target = 'y_change_t1'
    
    X_train, y_train = train[features], train[target]
    X_test, y_test = test[features], test[target]
    
    weights = 1 + (y_train.abs() * 5)
    
    model = HistGradientBoostingRegressor(max_depth=10, random_state=42)
    model.fit(X_train, y_train, sample_weight=weights)
    
    # --- CÁLCULO DE MÉTRICAS (Una sola vez) ---
    pred_model = model.predict(X_test)
    pred_base = np.zeros_like(pred_model)
    
    # Globales
    rmse_g = np.sqrt(mean_squared_error(y_test, pred_model))
    rmse_b = np.sqrt(mean_squared_error(y_test, pred_base))
    
    # Brotes
    umbral = y_test.abs().quantile(0.8)
    mask = y_test.abs() >= umbral
    rmse_g_out = np.sqrt(mean_squared_error(y_test[mask], pred_model[mask]))
    rmse_b_out = np.sqrt(mean_squared_error(y_test[mask], pred_base[mask]))
    
    metrics = {
        "global": {"rmse_model": round(rmse_g, 4), "rmse_base": round(rmse_b, 4)},
        "outbreak": {
            "rmse_model": round(rmse_g_out, 4), 
            "rmse_base": round(rmse_b_out, 4),
            "improvement": round(100 * (1 - rmse_g_out/rmse_b_out), 1)
        }
    }
    
    model_cache = {
        "model": model,
        "df_full": df_model, # Para graficar
        "metrics": metrics,
        "features": features
    }
    print(">>> [ML Engine] Modelo listo.")
    return model_cache

# --- ENDPOINTS NUEVOS ---

@app.get("/api/thailand/model/metrics")
def get_model_metrics():
    data = get_thai_model_resources()
    return data["metrics"]

@app.get("/api/thailand/model/graph")
def get_model_graph(province: str):
    """Retorna datos para graficar: Real vs Modelo vs Baseline para una provincia"""
    data = get_thai_model_resources()
    df = data["df_full"]
    model = data["model"]
    feats = data["features"]
    
    # Filtrar provincia (normalizar nombre por si acaso)
    prov_norm = province.strip().upper()
    d_prov = df[df['province_raw'].str.upper() == prov_norm].sort_values('date')
    
    if d_prov.empty:
        return {"error": "Provincia no encontrada"}
    
    # Filtrar solo validación (2024 en adelante) o todo el histórico si prefieres
    d_prov = d_prov[d_prov['date'].dt.year >= 2023] 
    
    # Predicciones
    # Real t+1
    real_vals = np.expm1(d_prov['log_cases'] + d_prov['y_change_t1'])
    # Predicción Modelo
    pred_vals = np.expm1(d_prov['log_cases'] + model.predict(d_prov[feats]))
    # Baseline
    base_vals = np.expm1(d_prov['log_cases'])
    
    return {
        "dates": d_prov['date_str'].tolist(),
        "real": real_vals.fillna(0).tolist(),
        "model": pred_vals.fillna(0).tolist(),
        "baseline": base_vals.fillna(0).tolist()
    }