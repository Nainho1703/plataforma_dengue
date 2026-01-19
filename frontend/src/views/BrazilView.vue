<template>
  <div class="layout-container">
    
    <div class="sidebar">
      <h2>🇧🇷 Monitor Dengue</h2>
      
      <div v-if="loadingWeeks" class="loading-text">Cargando fechas...</div>
      
      <div v-else class="controls-box">
        <div class="selectors">
          <div class="form-group">
            <label>Año:</label>
            <select v-model="selectedYear" @change="updateSliderFromDropdown">
              <option v-for="y in uniqueYears" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>
          
          <div class="form-group">
            <label>Semana:</label>
            <select v-model="selectedWeekOnly" @change="updateSliderFromDropdown">
              <option v-for="w in weeksInSelectedYear" :key="w" :value="w">{{ w }}</option>
            </select>
          </div>
        </div>

        <div class="slider-container">
          
          <div class="slider-row">
            
            <button 
              class="nav-btn" 
              @click="prevWeek" 
              :disabled="sliderIndex <= 0"
              title="Semana anterior"
            >
              ◀
            </button>

            <input 
              type="range" 
              min="0" 
              :max="allWeeks.length - 1" 
              v-model="sliderIndex" 
              @input="onSliderChange"
              class="slider"
            >

            <button 
              class="nav-btn" 
              @click="nextWeek" 
              :disabled="sliderIndex >= allWeeks.length - 1"
              title="Siguiente semana"
            >
              ▶
            </button>
            
          </div>

          <div class="slider-label">
            {{ currentWeekLabel }}
          </div>
        </div>
      </div>

      <div class="legend-box">
        <h4>Casos Semanales</h4>
        <div class="gradient-bar"></div>
        <div class="labels">
          <span>0</span>
          <span>50+</span>
          <span>500+</span>
        </div>
      </div>

      <div class="table-container">
        <h3>Municipios con Casos ({{ tableData.length }})</h3>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Municipio</th>
                <th>Casos</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableData" :key="row.id" @click="zoomToMunicipality(row.bounds)">
                <td>{{ row.name }}</td>
                <td class="cases-cell">{{ row.cases }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="tableData.length === 0" class="no-data">
            No hay casos registrados esta semana.
          </div>
        </div>
      </div>
    </div>

    <div class="map-area">
      <div id="map-brazil" class="map-frame"></div>
      <div v-if="loadingMap" class="map-loader">
        <div class="spinner"></div> Cargando mapa...
      </div>
    </div>

  </div>
</template>

<script setup>
import { onMounted, ref, computed, nextTick } from 'vue';
import L from 'leaflet';
import axios from 'axios';

// ESTADO
const allWeeks = ref([]); 
const sliderIndex = ref(0);
const loadingWeeks = ref(true);
const loadingMap = ref(false);
const tableData = ref([]); 
const mapError = ref(null); // Nuevo estado para errores visibles

// MAPA
let map = null;
let geoJsonLayer = null;

// COMPUTADOS
const currentWeekLabel = computed(() => allWeeks.value[sliderIndex.value] || 'Cargando...');
const uniqueYears = computed(() => {
  const years = new Set(allWeeks.value.map(w => w.split('-')[0]));
  return Array.from(years).sort().reverse();
});
const selectedYear = ref(""); 
const weeksInSelectedYear = computed(() => {
  if (!selectedYear.value) return [];
  return allWeeks.value.filter(w => w.startsWith(selectedYear.value)).map(w => w.split('-')[1]);
});
const selectedWeekOnly = ref(""); 

// INICIO
onMounted(async () => {
  initMap();
  try {
    const API_URL = import.meta.env.VITE_API_BASE_URL;

    const res = await axios.get(`${API_URL}/api/brasil/weeks`);


    allWeeks.value = res.data;
    console.log("📅 Semanas cargadas:", allWeeks.value.length); // ALARMA 1
    
    if (allWeeks.value.length > 0) {
      // Intentamos ir a una semana intermedia (a veces la última está vacía de datos)
      // O vamos a la última disponible
      sliderIndex.value = allWeeks.value.length - 1;
      syncDropdowns();
      fetchWeekData();
    }
  } catch (e) {
    console.error("Error cargando semanas:", e);
    mapError.value = "Error conectando con el servidor.";
  } finally {
    loadingWeeks.value = false;
  }
});




function initMap() {
  // Forzamos el renderizado del mapa
  map = L.map('map-brazil').setView([-14.2350, -51.9253], 4);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png').addTo(map);
}

async function fetchWeekData() {
  const week = allWeeks.value[sliderIndex.value];
  if (!week) return;

  loadingMap.value = true;
  mapError.value = null;

  try {
    console.log(`📡 Pidiendo datos para: ${week}...`); // ALARMA 2
    const API_URL = import.meta.env.VITE_API_BASE_URL;

    const res = await axios.get(`${API_URL}/api/brasil?week=${week}`);

    
    // --- DIAGNÓSTICO PROFUNDO ---
    const rawData = res.data;
    console.log("📦 RESPUESTA API:", rawData); // ALARMA 3
    
    if (!rawData.features || rawData.features.length === 0) {
        console.warn("⚠️ El GeoJSON vino vacío (0 features)");
        mapError.value = `La semana ${week} no tiene datos geográficos.`;
        loadingMap.value = false;
        return;
    }
    console.log(`✅ Pintando ${rawData.features.length} municipios...`);
    // -----------------------------

    if (geoJsonLayer) map.removeLayer(geoJsonLayer);
    
    const stats = [];

    geoJsonLayer = L.geoJson(rawData, {
      style: style,
      onEachFeature: (feature, layer) => {
        // 1. DEFINIMOS LA VARIABLE (Ojo: viene como 'casos' del backend)
        const valorCasos = feature.properties.casos || 0;
        
        // 2. Usamos 'valorCasos' para el Popup
        layer.bindPopup(`<strong>${feature.properties.NM_MUN}</strong><br>Casos: ${valorCasos}`);

        // 3. Usamos 'valorCasos' para la Tabla
        if (valorCasos > 0) {
          stats.push({
            id: feature.properties.id_join,
            name: feature.properties.NM_MUN,
            cases: valorCasos, // <--- AQUÍ ESTABA EL ERROR (antes decía cases: cases)
            bounds: layer.getBounds()
          });
        }
      }
    }).addTo(map);

    // AUTO ZOOM
    if (geoJsonLayer.getLayers().length > 0) {
        map.fitBounds(geoJsonLayer.getBounds());
    }

    tableData.value = stats.sort((a, b) => b.cases - a.cases);

  } catch (e) {
    console.error("Error mapa:", e);
    mapError.value = "Error cargando el mapa: " + e.message;
  } finally {
    loadingMap.value = false;
  }
}

function getColor(d) {
    return d > 500 ? '#800026' : d > 200 ? '#BD0026' : d > 100 ? '#E31A1C' :
           d > 50  ? '#FC4E2A' : d > 20  ? '#FD8D3C' : d > 10  ? '#FEB24C' :
           d > 0   ? '#FED976' : '#FFEDA0';
}
function style(feature) {
    return {
        fillColor: getColor(feature.properties.casos || 0),
        weight: 0.5,
        opacity: 1,
        color: 'white',
        fillOpacity: 0.7
    };
}

function prevWeek() {
  if (sliderIndex.value > 0) {
    sliderIndex.value--; // Restamos 1
    onSliderChange();    // Actualizamos todo (mapa y dropdowns)
  }
}

function nextWeek() {
  if (sliderIndex.value < allWeeks.value.length - 1) {
    sliderIndex.value++; // Sumamos 1
    onSliderChange();    // Actualizamos todo
  }
}
function syncDropdowns() {
  const currentWeekStr = allWeeks.value[sliderIndex.value]; 
  if(!currentWeekStr) return;
  const [y, w] = currentWeekStr.split('-');
  selectedYear.value = y;
  selectedWeekOnly.value = w;
}
function onSliderChange() { syncDropdowns(); fetchWeekData(); }
function updateSliderFromDropdown() {
  const target = `${selectedYear.value}-${selectedWeekOnly.value}`;
  const idx = allWeeks.value.indexOf(target);
  if (idx !== -1) { sliderIndex.value = idx; fetchWeekData(); }
}
function zoomToMunicipality(bounds) { map.fitBounds(bounds, { maxZoom: 10 }); }
</script>

<style scoped>
/* LAYOUT: Pantalla dividida (Izquierda controles, Derecha mapa) */
.layout-container {
  display: flex;
  height: calc(100vh - 60px); /* Restamos header si existe */
  overflow: hidden;
}

/* SIDEBAR */
.sidebar {
  width: 300px;
  background: #f8f9fa;
  border-right: 1px solid #ddd;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  box-shadow: 2px 0 5px rgba(0,0,0,0.05);
  z-index: 2;
}

.controls-box {
  margin-bottom: 20px;
  background: white;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #eee;
}

.selectors {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.form-group {
  flex: 1;
}
.form-group label {
  display: block;
  font-size: 0.8rem;
  color: #666;
  margin-bottom: 2px;
}
select {
  width: 100%;
  padding: 5px;
  border-radius: 4px;
  border: 1px solid #ccc;
}

.slider-container {
  text-align: center;
}
.slider {
  width: 100%;
  cursor: pointer;
}
.slider-label {
  font-weight: bold;
  color: #2c3e50;
  margin-top: 5px;
}

/* TABLA */
.table-container {
  flex: 1; /* Ocupa el espacio restante */
  display: flex;
  flex-direction: column;
  background: white;
  border: 1px solid #eee;
  border-radius: 8px;
  overflow: hidden;
}
.table-container h3 {
  font-size: 1rem;
  margin: 10px;
  color: #34495e;
}

.table-scroll {
  flex: 1;
  overflow-y: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
th {
  background: #eee;
  position: sticky;
  top: 0;
  padding: 8px;
  text-align: left;
  font-size: 0.8rem;
}
td {
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
}
tr:hover {
  background-color: #e3f2fd;
}
.cases-cell {
  font-weight: bold;
  color: #e74c3c;
  text-align: right;
}

/* MAPA */
.map-area {
  flex: 1;
  position: relative;
}
.map-frame {
  width: 100%;
  height: 100%;
}
.map-loader {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(255,255,255,0.9);
  padding: 20px;
  border-radius: 10px;
  font-weight: bold;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 10px;
}
.spinner {
  width: 20px;
  height: 20px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

/* LEYENDA */
.legend-box {
  margin-bottom: 15px;
  padding: 10px;
  background: white;
  border-radius: 4px;
}
.gradient-bar {
  height: 10px;
  background: linear-gradient(to right, #FFEDA0, #800026);
  border-radius: 2px;
}
.labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  margin-top: 4px;
}


/* Nuevo contenedor para alinear horizontalmente */
.slider-row {
  display: flex;
  align-items: center;
  gap: 10px; /* Espacio entre flechas y slider */
}

/* Estilo de los botones de flecha */
.nav-btn {
  background: #3498db;
  color: white;
  border: none;
  border-radius: 50%; /* Redondos */
  width: 30px;
  height: 30px;
  cursor: pointer;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.nav-btn:hover:not(:disabled) {
  background: #2980b9;
}

.nav-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
  opacity: 0.5;
}

/* Ajuste para que el slider ocupe el espacio restante */
.slider {
  flex: 1; 
  cursor: pointer;
}
</style>