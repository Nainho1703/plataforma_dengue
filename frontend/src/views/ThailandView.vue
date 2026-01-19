<template>
  <div class="layout-container">
    
    <div class="sidebar">
      <h2>🇹🇭 Dengue Tailandia</h2>
      
      <div v-if="loadingDates" class="loading-text">
        <div class="spinner-small"></div> Cargando datos...
      </div>
      
      <div v-else class="controls-box">
        
        <div class="selectors-row">
          <div class="form-group">
            <label>Año:</label>
            <select v-model="selectedYear" @change="onYearChange">
              <option v-for="y in uniqueYears" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>

          <div class="form-group">
            <label>Mes:</label>
            <select v-model="selectedMonth" @change="onMonthChange">
              <option value="" disabled>--</option>
              <option v-for="(name, index) in monthNames" :key="index" :value="index + 1">
                {{ name }}
              </option>
            </select>
          </div>
        </div>

        <div class="metric-selector">
          <label>Ver por:</label>
          <select v-model="selectedMetric" @change="updateVisualization">
            <option value="cases">🦟 Casos Totales</option>
            <option value="incidence">📊 Incidencia (x 100k hab)</option>
          </select>
        </div>

        <div class="slider-container">
          <div class="slider-row">
            <button 
              class="nav-btn" 
              @click="prevDate" 
              :disabled="isFirstMonthOfAll"
              title="Mes Anterior"
            >◀</button>
            
            <input 
              type="range" 
              min="0" 
              :max="filteredDates.length - 1" 
              v-model.number="sliderIndex" 
              class="slider"
            >
            
            <button 
              class="nav-btn" 
              @click="nextDate" 
              :disabled="isLastMonthOfAll"
              title="Mes Siguiente"
            >▶</button>
          </div>
        </div>

      </div>

      <div class="legend-box">
        <h4>{{ legendTitle }}</h4>
        <div class="gradient-bar"></div>
        <div class="labels">
          <span v-for="label in currentLegendLabels" :key="label">{{ label }}</span>
        </div>
      </div>
      
      <div class="table-container">
        <h3>Ranking ({{ tableData.length }})</h3>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Provincia</th>
                <th>{{ selectedMetric === 'cases' ? 'Casos' : 'Incidencia' }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableData" :key="row.name" @click="zoomToFeature(row.bounds)">
                <td>{{ row.name }}</td>
                <td class="cases-cell">{{ row.valueDisplay }}</td>
              </tr>
              <tr v-if="tableData.length === 0">
                <td colspan="2" style="text-align:center; padding:20px; color:#999;">
                  Sin datos
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="map-area">
      <div id="map-thai" class="map-frame"></div>
      
      <div v-if="loadingMap" class="map-overlay">
        <div class="spinner"></div>
        <span>Cargando...</span>
      </div>
    </div>

  </div>
</template>

<script setup>
import { onMounted, ref, computed, watch } from 'vue';
import L from 'leaflet';
import axios from 'axios';
import 'leaflet/dist/leaflet.css';

// --- CONFIGURACIÓN ---
const monthNames = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
];

// --- ESTADOS ---
const allDates = ref([]);      
const filteredDates = ref([]); 
const sliderIndex = ref(0);
const selectedYear = ref("");
const selectedMonth = ref("");
const selectedMetric = ref("cases");

const loadingDates = ref(true);
const loadingMap = ref(false);
const tableData = ref([]);

let map = null;
let geoJsonLayer = null;
let currentGeoJsonData = null; 

// --- COMPUTADOS ---

const uniqueYears = computed(() => {
  const years = new Set(allDates.value.map(d => d.split('-')[0]));
  return Array.from(years).sort().reverse(); // [2024, 2023, ...]
});

const currentDateRaw = computed(() => filteredDates.value[sliderIndex.value]);

// Detectar límites globales para deshabilitar botones
const isFirstMonthOfAll = computed(() => {
  // Es el primer año Y el primer mes (índice 0)
  return selectedYear.value === uniqueYears.value[uniqueYears.value.length - 1] && sliderIndex.value === 0;
});

const isLastMonthOfAll = computed(() => {
  // Es el último año Y el último mes
  return selectedYear.value === uniqueYears.value[0] && sliderIndex.value === filteredDates.value.length - 1;
});

const legendTitle = computed(() => selectedMetric.value === 'cases' ? 'Casos Mensuales' : 'Incidencia / 100k hab');

const currentLegendLabels = computed(() => {
  if (selectedMetric.value === 'cases') return ['0', '50', '200', '500+'];
  else return ['0', '10', '50', '100+'];
});

// --- CICLO DE VIDA ---

onMounted(async () => {
  initMap();
  await loadDates();
});

// WATCHER MAESTRO:
// Vigilamos 'currentDateRaw'. Si cambia (por slider o por cambio de año), cargamos datos.
watch(currentDateRaw, (newVal) => {
  if (newVal) {
    syncMonthDropdown();
    fetchData();
  }
});

// --- FUNCIONES ---

async function loadDates() {
  try {

    const API_URL = import.meta.env.VITE_API_BASE_URL;

    const res = await axios.get(`${API_URL}/api/thailand/dates`);

    allDates.value = res.data;
    
    if (allDates.value.length > 0) {
      const lastDate = allDates.value[allDates.value.length - 1];
      selectedYear.value = lastDate.split('-')[0];
      filterDatesByYear(true); // true = ir al final
    }
  } catch (e) { console.error(e); } 
  finally { loadingDates.value = false; }
}

function initMap() {
  map = L.map('map-thai').setView([15.8700, 100.9925], 6);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png').addTo(map);
}

// Filtra las fechas. "goToEnd" sirve para cuando volvemos del año siguiente (Ene -> Dic)
function filterDatesByYear(goToEnd = false) {
  filteredDates.value = allDates.value.filter(d => d.startsWith(selectedYear.value));
  // Si pedimos ir al final, ponemos el slider en el último mes. Si no, al principio.
  sliderIndex.value = goToEnd ? filteredDates.value.length - 1 : 0;
  syncMonthDropdown();
}

// --- NAVEGACIÓN INTELIGENTE (LA CLAVE) ---

function prevDate() {
  // Caso 1: Aún hay meses antes en este año
  if (sliderIndex.value > 0) {
    sliderIndex.value--;
  } 
  // Caso 2: Estamos en Enero -> Intentamos ir al año anterior
  else {
    const currentY = parseInt(selectedYear.value);
    const prevY = (currentY - 1).toString();
    
    if (uniqueYears.value.includes(prevY)) {
      selectedYear.value = prevY;
      filterDatesByYear(true); // true = ¡Ponme en Diciembre!
    }
  }
}

function nextDate() {
  // Caso 1: Aún hay meses después en este año
  if (sliderIndex.value < filteredDates.value.length - 1) {
    sliderIndex.value++;
  } 
  // Caso 2: Estamos en Diciembre -> Intentamos ir al año siguiente
  else {
    const currentY = parseInt(selectedYear.value);
    const nextY = (currentY + 1).toString();
    
    if (uniqueYears.value.includes(nextY)) {
      selectedYear.value = nextY;
      filterDatesByYear(false); // false = ¡Ponme en Enero!
    }
  }
}

// --- OTROS EVENTOS ---

function onYearChange() { filterDatesByYear(); }

function onMonthChange() {
  const monthStr = String(selectedMonth.value).padStart(2, '0');
  const targetPrefix = `${selectedYear.value}-${monthStr}`;
  const idx = filteredDates.value.findIndex(d => d.startsWith(targetPrefix));
  if (idx !== -1) sliderIndex.value = idx;
  else { alert("Sin datos."); syncMonthDropdown(); }
}

function syncMonthDropdown() {
  if (!currentDateRaw.value) return;
  const parts = currentDateRaw.value.split('-'); 
  if (parts.length >= 2) selectedMonth.value = parseInt(parts[1], 10);
}

function updateVisualization() {
  if (!currentGeoJsonData) return;
  if (geoJsonLayer) map.removeLayer(geoJsonLayer);
  
  const stats = [];
  
  geoJsonLayer = L.geoJson(currentGeoJsonData, {
    style: style,
    onEachFeature: (feature, layer) => {
      const props = feature.properties;
      const casos = props.cases || 0;
      const inc = props.incidence || 0;
      const pop = props.Population || 0;
      const nombre = props.province_display || "Desconocido";

      layer.bindPopup(`
          <div style="text-align:center; min-width:120px;">
              <strong>${nombre}</strong><hr style="margin:5px 0;">
              <div>🦟 Casos: <b>${casos}</b></div>
              <div>📊 Incidencia: <b>${inc}</b></div>
              <div style="font-size:0.8em; color:#666;">Pop: ${pop.toLocaleString()}</div>
          </div>
      `);
      
      const val = selectedMetric.value === 'cases' ? casos : inc;
      if (val > 0) {
        stats.push({ 
          name: nombre, 
          value: val, 
          valueDisplay: val.toLocaleString(),
          bounds: layer.getBounds() 
        });
      }
    }
  }).addTo(map);
  
  tableData.value = stats.sort((a,b) => b.value - a.value);
}

async function fetchData() {
  const date = currentDateRaw.value;
  if (!date) return;
  
  loadingMap.value = true;
  try {

    const API_URL = import.meta.env.VITE_API_BASE_URL;

    const res = await axios.get(`${API_URL}/api/thailand/data?date=${date}`);

    
    currentGeoJsonData = res.data;
    updateVisualization();
  } catch (e) {
    console.error(e);
  } finally {
    loadingMap.value = false;
  }
}

function zoomToFeature(bounds) { map.fitBounds(bounds); }

// --- ESTILOS ---
function getColor(d) {
  if (selectedMetric.value === 'cases') {
      return d > 500 ? '#800026' : d > 200 ? '#BD0026' : d > 100 ? '#E31A1C' :
             d > 50  ? '#FC4E2A' : d > 20  ? '#FD8D3C' : d > 0   ? '#FED976' : '#FFEDA0';
  } else {
      return d > 100 ? '#800026' : d > 50  ? '#BD0026' : d > 25  ? '#E31A1C' :
             d > 10  ? '#FC4E2A' : d > 5   ? '#FD8D3C' : d > 0   ? '#FED976' : '#FFEDA0';
  }
}

function style(feature) {
  const val = feature.properties[selectedMetric.value] || 0;
  return { fillColor: getColor(val), weight: 1, color: 'white', fillOpacity: 0.7 };
}
</script>

<style scoped>
/* Reutilizamos los mismos estilos previos */
.layout-container { display: flex; height: 90vh; font-family: 'Segoe UI', sans-serif; }
.sidebar { width: 320px; padding: 20px; background: #f8f9fa; display: flex; flex-direction: column; border-right: 1px solid #ddd; z-index: 2; box-shadow: 2px 0 5px rgba(0,0,0,0.05); }
.controls-box { background: white; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 20px; }
.selectors-row { display: flex; gap: 10px; margin-bottom: 10px; }
.form-group { flex: 1; }
.form-group label, .metric-selector label { display: block; font-size: 0.8rem; color: #666; margin-bottom: 4px; }
select { width: 100%; padding: 6px; border-radius: 4px; border: 1px solid #ccc; background: #fff; }
.metric-selector { margin-bottom: 15px; }
.metric-selector select { font-weight: bold; color: #2c3e50; border-color: #3498db; }
.slider-container { margin-top: 15px; text-align: center; }
.slider-row { display: flex; align-items: center; gap: 8px; }
.slider { flex: 1; cursor: pointer; }
.nav-btn { background: #3498db; color: white; border: none; border-radius: 50%; width: 28px; height: 28px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.nav-btn:hover:not(:disabled) { background: #2980b9; }
.nav-btn:disabled { background: #ccc; cursor: not-allowed; opacity: 0.5; }
.legend-box { background: white; padding: 10px; border-radius: 8px; border: 1px solid #eee; margin-bottom: 15px; }
.gradient-bar { height: 12px; background: linear-gradient(to right, #FFEDA0, #800026); border-radius: 3px; margin: 8px 0; }
.labels { display: flex; justify-content: space-between; font-size: 0.75rem; color: #555; }
.table-container { flex: 1; overflow: hidden; display: flex; flex-direction: column; background: white; border: 1px solid #eee; border-radius: 8px; }
.table-scroll { flex: 1; overflow-y: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { position: sticky; top: 0; background: #f1f1f1; padding: 8px; text-align: left; font-size: 0.8rem; z-index: 1; }
td { padding: 8px; border-bottom: 1px solid #f9f9f9; }
tr:hover { background-color: #eaf6ff; cursor: pointer; }
.cases-cell { color: #c0392b; font-weight: bold; text-align: right; }
.map-area { flex: 1; position: relative; }
.map-frame { width: 100%; height: 100%; }
.map-overlay { position: absolute; top: 20px; left: 50%; transform: translateX(-50%); background: rgba(255,255,255,0.95); padding: 10px 20px; border-radius: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); z-index: 1000; display: flex; align-items: center; gap: 10px; font-weight: 600; color: #333; }
.spinner { width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; }
.spinner-small { width: 15px; height: 15px; border: 2px solid #ccc; border-top: 2px solid #333; border-radius: 50%; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>