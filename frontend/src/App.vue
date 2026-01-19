<script setup>
import { ref } from "vue";

// Importar las vistas existentes
import MapDengue from "./views/WorldView.vue"; 
import ThailandView from "./views/ThailandView.vue"; 
import ArgentinaView from "./views/ArgentinaView.vue";
import BangkokView from "./views/BangkokView.vue";

// 1. IMPORTAR LA NUEVA VISTA DE BRASIL
import BrazilView from "./views/BrazilView.vue"; 

// Estado de navegación
const currentView = ref("world");
</script>

<template>
  <div class="app-layout">
    <nav class="nav-header">
      <div class="brand">🦟 Dengue Tracker</div>
      <div class="nav-buttons">
        
        <button :class="{ active: currentView === 'world' }" @click="currentView = 'world'">
          🌍 Ámericas
        </button>
        <button :class="{ active: currentView === 'arg' }" @click="currentView = 'arg'">
          🇦🇷 Argentina
        </button>

        <button :class="{ active: currentView === 'bra' }" @click="currentView = 'bra'">
          🇧🇷 Brasil
        </button>

          <button :class="{ active: currentView === 'thai' }" @click="currentView = 'thai'">
          🇹🇭 Thailand
        </button>
        <button :class="{ active: currentView === 'bang' }" @click="currentView = 'bang'">
          🇹🇭 Bangkok
        </button>


      </div>
    </nav>

    <div class="content-area">
      <MapDengue v-if="currentView === 'world'" />
      <ThailandView v-if="currentView === 'thai'" />
      <BangkokView v-if="currentView === 'bang'" />
      <ArgentinaView v-if="currentView === 'arg'" />
      <ModelsView v-if="currentView === 'models'" />

      <BrazilView v-if="currentView === 'bra'" />
    </div>
  </div>
</template>

<style scoped>
/* Tu estilo CSS se mantiene igual, no hace falta tocarlo */
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.nav-header {
  background-color: #2c3e50;
  color: white;
  padding: 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  font-size: 1.2rem;
  font-weight: bold;
}

.nav-buttons button {
  background: transparent;
  border: 1px solid transparent;
  color: #bdc3c7;
  padding: 0.5rem 1rem;
  margin-left: 0.5rem;
  cursor: pointer;
  border-radius: 4px;
  font-size: 1rem;
  transition: all 0.3s;
}

.nav-buttons button:hover {
  color: white;
  background-color: rgba(255,255,255,0.1);
}

.nav-buttons button.active {
  background-color: #34495e;
  color: #3498db;
  border-color: #3498db;
  font-weight: bold;
}

.content-area {
  flex: 1;
  position: relative;
  overflow: hidden;
}
</style>