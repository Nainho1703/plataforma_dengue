<template>
  <div class="layout-container">
    
    <div class="sidebar">
      <h2>🇧🇷 Monitor Dengue</h2>
      
      <div v-if="loadingWeeks" class="loading-text">
        <div class="spinner-small"></div> Cargando calendario...
      </div>
      
      <div v-else class="controls-box">
        <div class="selectors">
          <div class="form-group">
            <label>Año:</label>
            <select v-model="selectedYear" @change="onYearChange">
              <option v-for="y in uniqueYears" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>
          
          <div class="form-group">
            <label>Semana:</label>
            <select v-model="selectedWeekNum" @change="onWeekDropdownChange">
              <option v-for="w in weeksInSelectedYear" :key="w" :value="w">{{ w }}</option>
            </select>
          </div>
        </div>

        <div class="slider-container">
          <div class="slider-row">
            <button 
              class="nav-btn" 
              @click="prevWeek" 
              :disabled="selectedWeekIndex <= 0"
              title="Semana anterior"
            >◀</button>

            <input 
              type="range" 
              min="0" 
              :max="weeks.length - 1" 
              v-model.number="selectedWeekIndex" 
              class="slider"
            >

            <button 
              class="nav-btn" 
              @click="nextWeek" 
              :disabled="selectedWeekIndex >= weeks.length - 1"
              title="Siguiente semana"
            >▶</button>
            
            <button 
              class="nav-btn btn-play" 
              @click="togglePlay" 
              :title="isPlaying ? 'Pausar' : 'Reproducir animación'"
            >
              {{ isPlaying ? '⏸' : '▶' }}
            </button>
          </div>

          <div class="slider-label">
            Semana: <strong>{{ currentWeek }}</strong>
          </div>
        </div>
      </div>

      <div class="legend-box">
        <h4>Casos Semanales</h4>
        <div class="gradient-bar"></div>
        <div class="labels">
          <span>0</span>
          <span>50</span>
          <span>200</span>
          <span>500</span>
          <span>1000+</span>
        </div>
      </div>

      <div class="table-container">
        <h3>Municipios con Casos ({{ tableData.length }})</h3>
        
        <div v-if="loadingMap" class="table-loading">Actualizando datos...</div>
        
        <div v-else class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Municipio</th>
                <th>Casos</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableData" :key="row.id" @click="zoomToMunicipality(row)">
                <td>{{ row.name }}</td>
                <td class="cases-cell">{{ row.cases }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!loadingMap && tableData.length === 0" class="no-data">
            Sin casos registrados o datos no disponibles.
          </div>
        </div>
      </div>
    </div>

    <div class="map-area">
      <div ref="mapContainer" class="map-frame"></div>
      
      <div v-if="loadingMap" class="map-loader">
        <div class="spinner"></div> Cargando mapa...
      </div>
      
      <div v-if="error" class="error-toast">{{ error }}</div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, onUnmounted, nextTick } from 'vue';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// --- ESTADO ---
const weeks = ref([]); 
const selectedWeekIndex = ref(0);
const loadingWeeks = ref(false); // Carga inicial de lista
const loadingMap = ref(false);   // Carga de cada GeoJSON
const error = ref(null);
const isPlaying = ref(false);
let playInterval = null;

// Datos actuales del GeoJSON (para llenar la tabla)
const currentGeoJsonData = ref(null);

// Dropdowns
const selectedYear = ref("");
const selectedWeekNum = ref("");

// Caché
const dataCache = new Map();

// Mapa
const mapContainer = ref(null); // Referencia al DIV
let map = null;
let geoJsonLayer = null;

// URL API
const API_URL = import.meta.env.VITE_API_BASE_URL;
const API_BASE = `${API_URL}/api`; 

// --- COMPUTADAS ---

const currentWeek = computed(() => {
  if (weeks.value.length === 0) return '';
  return weeks.value[selectedWeekIndex.value];
});

// Extraer Años únicos
const uniqueYears = computed(() => {
  const years = new Set(weeks.value.map(w => w.split('-')[0]));
  return Array.from(years).sort();
});

// Semanas disponibles en el año seleccionado
const weeksInSelectedYear = computed(() => {
  if (!selectedYear.value) return [];
  return weeks.value
    .filter(w => w.startsWith(selectedYear.value))
    .map(w => w.split('-')[1]);
});

// Generar datos para la tabla dinámicamente desde el GeoJSON cargado
const tableData = computed(() => {
  if (!currentGeoJsonData.value) return [];
  
  const rows = [];
  currentGeoJsonData.value.features.forEach(f => {
    const props = f.properties;
    const casos = props.casos || 0;
    
    // Solo mostramos si tienen casos para no saturar la tabla (opcional)
    if (casos > 0) {
      rows.push({
        id: props.ID_MN_RESI || Math.random(), // ID único
        name: props.NM_MUN || props.name || "Desconocido",
        cases: casos,
        geometry: f.geometry // Guardamos geometría para el zoom
      });
    }
  });

  // Ordenar de mayor a menor casos
  return rows.sort((a, b) => b.cases - a.cases);
});

// --- CICLO DE VIDA ---
onMounted(async () => {
  await nextTick(); // Asegura que el DOM existe
  initMap();
  await loadWeeks();
});

onUnmounted(() => {
  stopPlay();
  if (map) { map.remove(); map = null; }
});

// --- MAPA ---

const initMap = () => {
  if (!mapContainer.value) return;
  
  map = L.map(mapContainer.value).setView([-14.2350, -51.9253], 4); 
  
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(map);
};

const loadWeeks = async () => {
  try {
    loadingWeeks.value = true;
    const res = await axios.get(`${API_BASE}/brasil/weeks`);
    weeks.value = res.data;
    
    if (weeks.value.length > 0) {
      // Seleccionar última semana
      selectedWeekIndex.value = weeks.value.length - 1;
      syncDropdownsFromIndex();
    }
  } catch (e) {
    error.value = "Error conectando API: " + e.message;
  } finally {
    loadingWeeks.value = false;
  }
};

const loadWeekData = async () => {
  const week = currentWeek.value;
  if (!week) return;

  // CACHÉ
  if (dataCache.has(week)) {
    const data = dataCache.get(week);
    currentGeoJsonData.value = data; // Actualizar datos para tabla
    updateMapLayer(data);
    return;
  }

  try {
    if (!isPlaying.value) loadingMap.value = true;

    const res = await axios.get(`${API_BASE}/brasil`, { params: { week: week } });
    const data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
    
    dataCache.set(week, data);
    currentGeoJsonData.value = data; // Guardar para tabla
    updateMapLayer(data);
    
  } catch (e) {
    console.error(e);
    error.value = "Error cargando mapa";
  } finally {
    loadingMap.value = false;
  }
};

const updateMapLayer = (data) => {
  if (geoJsonLayer) {
    geoJsonLayer.clearLayers();
    map.removeLayer(geoJsonLayer);
  }
  
  geoJsonLayer = L.geoJSON(data, {
    style: styleFeature,
    onEachFeature: onEachFeature
  }).addTo(map);
};

// --- LOGICA DE UI (DROPDOWNS y ZOOM) ---

// Sincronizar Dropdowns cuando cambia el Slider
const syncDropdownsFromIndex = () => {
  const current = weeks.value[selectedWeekIndex.value];
  if (current) {
    const [y, w] = current.split('-');
    selectedYear.value = y;
    selectedWeekNum.value = w;
  }
};

// Cambio manual de Año
const onYearChange = () => {
  const target = weeks.value.find(w => w.startsWith(selectedYear.value));
  if (target) selectedWeekIndex.value = weeks.value.indexOf(target);
};

// Cambio manual de Semana
const onWeekDropdownChange = () => {
  const target = `${selectedYear.value}-${selectedWeekNum.value}`;
  const idx = weeks.value.indexOf(target);
  if (idx !== -1) selectedWeekIndex.value = idx;
};

// Zoom al municipio al hacer click en la tabla
const zoomToMunicipality = (row) => {
  if (!row.geometry) return;
  // Crear capa temporal Leaflet para obtener los límites (bounds)
  const layer = L.geoJSON(row.geometry);
  const bounds = layer.getBounds();
  map.fitBounds(bounds, { padding: [50, 50], maxZoom: 10 });
  
  // Resaltar visualmente (Opcional: podrías abrir el popup)
  L.popup()
    .setLatLng(bounds.getCenter())
    .setContent(`<b>${row.name}</b><br>Casos: ${row.cases}`)
    .openOn(map);
};

// --- CONTROLES NAVEGACIÓN ---
const prevWeek = () => { if (selectedWeekIndex.value > 0) selectedWeekIndex.value--; };
const nextWeek = () => { if (selectedWeekIndex.value < weeks.value.length - 1) selectedWeekIndex.value++; };

const togglePlay = () => isPlaying.value ? stopPlay() : startPlay();

const startPlay = () => {
  isPlaying.value = true;
  playInterval = setInterval(() => {
    if (selectedWeekIndex.value < weeks.value.length - 1) selectedWeekIndex.value++;
    else selectedWeekIndex.value = 0;
  }, 1500);
};

const stopPlay = () => {
  isPlaying.value = false;
  if (playInterval) clearInterval(playInterval);
};

// Watcher principal
watch(selectedWeekIndex, () => {
  loadWeekData();
  syncDropdownsFromIndex();
});

// --- ESTILOS MAPA ---
const getColor = (d) => {
  return d > 1000 ? '#800026' : d > 500 ? '#BD0026' : d > 200 ? '#E31A1C' :
         d > 100 ? '#FC4E2A' : d > 50 ? '#FD8D3C' : d > 0 ? '#FED976' : '#FFEDA0';
};

const styleFeature = (feature) => ({
  fillColor: getColor(feature.properties.casos || 0),
  weight: 1, opacity: 1, color: 'white', dashArray: '3', fillOpacity: 0.7
});

const onEachFeature = (feature, layer) => {
  const props = feature.properties;
  const nombre = props.NM_MUN || props.name || "Municipio"; 
  layer.bindPopup(`<strong>${nombre}</strong><br/>Casos: ${props.casos || 0}`);
};
</script>

<style scoped>
/* ESTILOS PRESERVADOS Y MEJORADOS */
.layout-container { display: flex; height: 90vh; overflow: hidden; font-family: 'Segoe UI', sans-serif; }

/* SIDEBAR */
.sidebar {
  width: 320px; flex-shrink: 0; background: #f8f9fa; border-right: 1px solid #ddd;
  display: flex; flex-direction: column; padding: 1rem; z-index: 2;
}
.sidebar h2 { margin: 0 0 15px 0; font-size: 1.2rem; color: #2c3e50; text-align: center; }

.controls-box { background: white; padding: 15px; border-radius: 8px; border: 1px solid #eee; margin-bottom: 15px; }

.selectors { display: flex; gap: 10px; margin-bottom: 10px; }
.form-group { flex: 1; }
.form-group label { display: block; font-size: 0.75rem; color: #666; margin-bottom: 2px; }
select { width: 100%; padding: 4px; border: 1px solid #ccc; border-radius: 4px; }

.slider-container { text-align: center; }
.slider-row { display: flex; align-items: center; gap: 8px; }
.slider { flex: 1; cursor: pointer; }
.slider-label { font-size: 0.9rem; margin-top: 5px; color: #333; }

.nav-btn {
  background: #3498db; color: white; border: none; border-radius: 4px;
  width: 28px; height: 28px; cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.nav-btn:disabled { background: #ccc; cursor: not-allowed; }
.btn-play { background: #27ae60; font-weight: bold; }

/* LEYENDA */
.legend-box { background: white; padding: 10px; border-radius: 4px; border: 1px solid #eee; margin-bottom: 15px; }
.legend-box h4 { margin: 0 0 5px 0; font-size: 0.8rem; }
.gradient-bar { height: 8px; background: linear-gradient(to right, #FFEDA0, #800026); border-radius: 2px; }
.labels { display: flex; justify-content: space-between; font-size: 0.65rem; margin-top: 3px; }

/* TABLA */
.table-container { flex: 1; display: flex; flex-direction: column; background: white; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
.table-container h3 { font-size: 0.9rem; margin: 10px; color: #34495e; text-align: center; }
.table-scroll { flex: 1; overflow-y: auto; }
.table-loading, .no-data { padding: 20px; text-align: center; font-size: 0.85rem; color: #777; }

table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { background: #f1f1f1; position: sticky; top: 0; padding: 6px; text-align: left; font-size: 0.75rem; z-index: 1; }
td { padding: 6px; border-bottom: 1px solid #f9f9f9; cursor: pointer; }
tr:hover { background-color: #e8f4fc; }
.cases-cell { font-weight: bold; color: #c0392b; text-align: right; }

/* MAPA */
.map-area { flex: 1; position: relative; }
.map-frame { width: 100%; height: 100%; background: #e5e5e5; }

.map-loader {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  background: rgba(255,255,255,0.95); padding: 15px 25px; border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1); font-weight: bold; color: #555;
  display: flex; align-items: center; gap: 10px; z-index: 9999;
}
.spinner { width: 18px; height: 18px; border: 3px solid #ddd; border-top-color: #3498db; border-radius: 50%; animation: spin 0.8s linear infinite; }
.spinner-small { width: 12px; height: 12px; border: 2px solid #ccc; border-top-color: #333; border-radius: 50%; animation: spin 0.8s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }
.error-toast { position: absolute; top: 10px; right: 10px; background: #e74c3c; color: white; padding: 10px; border-radius: 4px; z-index: 9999; font-size: 0.8rem; }
</style>