import { createRouter, createWebHistory } from 'vue-router'
// Importa tus vistas existentes
import HomeView from '../views/HomeView.vue'
import ThailandView from '../views/ThailandView.vue' 
import BangkokView from '../views/BangkokView.vue' 
// 1. IMPORTA TU NUEVA VISTA AQUÍ
import ArgentinaView from '../views/ArgentinaView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/thailand',
      name: 'thailand',
      component: ThailandView
    },
    {
      path: '/bangkok',
      name: 'bangkok',
      component: BangkokView
    },
    // 2. AGREGA LA NUEVA RUTA AQUÍ
    {
      path: '/argentina',   // La URL que aparecerá en el navegador
      name: 'argentina',    // Nombre interno para usar en el código
      component: ArgentinaView
    }
  ]
})

export default router