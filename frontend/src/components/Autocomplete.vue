<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  label: { type: String, default: '' },
  items: { type: Array, default: () => [] },
  modelValue: { type: [String, Number], default: '' },
  displayFn: { type: Function, default: (item) => item?.descripcion || item?.nombre || String(item?.id || '') },
  placeholder: { type: String, default: 'Buscar...' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const query = ref('')
const open = ref(false)

const selectedItem = computed(() => {
  return props.items.find((item) => String(item.id) === String(props.modelValue)) || null
})

const selectedLabel = computed(() => selectedItem.value ? props.displayFn(selectedItem.value) : '')

watch(selectedLabel, (value) => {
  query.value = value
}, { immediate: true })

const filteredItems = computed(() => {
  const search = query.value.trim().toLowerCase()
  if (!search || search === selectedLabel.value.toLowerCase()) return props.items.slice(0, 20)

  return props.items
    .filter((item) => props.displayFn(item).toLowerCase().includes(search))
    .slice(0, 20)
})

const selectItem = (item) => {
  emit('update:modelValue', item.id)
  query.value = props.displayFn(item)
  open.value = false
}

const clearSelection = () => {
  emit('update:modelValue', '')
  query.value = ''
  open.value = true
}
</script>

<template>
  <div class="relative">
    <label v-if="label" class="mb-1 block text-xs font-medium text-gray-500">{{ label }}</label>

    <div class="flex gap-2">
      <input
        v-model="query"
        type="text"
        :disabled="disabled"
        :placeholder="placeholder"
        class="w-full rounded border p-2 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
        @focus="open = !disabled"
        @input="open = !disabled"
      >
      <button
        v-if="!disabled && modelValue"
        type="button"
        class="rounded border border-gray-300 px-3 text-sm text-gray-600 dark:border-gray-700 dark:text-gray-200"
        @click="clearSelection"
      >
        Limpiar
      </button>
    </div>

    <div
      v-if="open && !disabled"
      class="absolute z-40 mt-1 max-h-60 w-full overflow-auto rounded-md border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
    >
      <button
        v-for="item in filteredItems"
        :key="item.id"
        type="button"
        class="block w-full px-3 py-2 text-left text-sm hover:bg-blue-50 dark:hover:bg-gray-700"
        @mousedown.prevent="selectItem(item)"
      >
        {{ displayFn(item) }}
      </button>
      <div v-if="filteredItems.length === 0" class="px-3 py-2 text-sm text-gray-500">
        Sin resultados
      </div>
    </div>
  </div>
</template>
