import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import NewTrip from '../views/NewTrip.vue'
import TripImageUpload from '../views/TripImageUpload.vue'
import Dashboard from '../views/Dashboard.vue'
import History from '../views/History.vue'
import Settings from '../views/Settings.vue'
import FuelLoad from '../views/FuelLoad.vue'
import CarretonMove from '../views/CarretonMove.vue'
import AdminClientLogs from '../views/AdminClientLogs.vue'
import AdminDashboard from '../views/AdminDashboard.vue'
import { resolveAuthNavigation } from './authGuard.js'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: Login, meta: { hideNavbar: true } },
  { path: '/dashboard', component: Dashboard, meta: { requiresAuth: true } },
  { path: '/new-trip', component: NewTrip, meta: { requiresAuth: true } },
  { path: '/new-trip/image', component: TripImageUpload, meta: { requiresAuth: true } },
  { path: '/history', component: History, meta: { requiresAuth: true } },
  { path: '/fuel-load', component: FuelLoad, meta: { requiresAuth: true } },
  { path: '/carreton-move', component: CarretonMove, meta: { requiresAuth: true } },
  { path: '/settings', component: Settings, meta: { requiresAuth: true } },
  { path: '/admin/dashboard', component: AdminDashboard, meta: { requiresAuth: true, requiresAdmin: true } },
  { path: '/admin/logs', component: AdminClientLogs, meta: { requiresAuth: true, requiresAdmin: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => resolveAuthNavigation(to))

export default router
