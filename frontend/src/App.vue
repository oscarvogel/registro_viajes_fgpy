<script setup>
import BottomNav from './components/BottomNav.vue';
import TopNav from './components/TopNav.vue';
import OfflineBanner from './components/OfflineBanner.vue';
import { useRoute } from 'vue-router';

const route = useRoute();
</script>

<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 pb-16">
    <!-- Skip link for keyboard users -->
    <a class="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 bg-white p-2 rounded shadow" href="#main-content">Saltar al contenido</a>

    <TopNav v-if="!route.meta.hideNavbar" />

    <!-- Offline / update banners -->
    <OfflineBanner />

    <main id="main-content">
      <router-view></router-view>
    </main>

    <BottomNav v-if="!route.meta.hideNavbar" />
  </div>
</template>
