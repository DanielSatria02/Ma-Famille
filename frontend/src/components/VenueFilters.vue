<script setup>
import { computed } from 'vue'
import '../styles/venue-filters.css'

// Groups come from the API (the facility kinds and venue tags actually in use),
// so the panel never offers a filter that matches nothing.
// groups: [{ key, title, options: [{ value, label }] }]
// modelValue: { [groupKey]: string[] }
const props = defineProps({
  groups: { type: Array, default: () => [] },
  modelValue: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue'])

const selected = computed(() => props.modelValue)

function isChecked(groupKey, value) {
  return (selected.value[groupKey] ?? []).includes(value)
}

function toggle(groupKey, value, checked) {
  const current = selected.value[groupKey] ?? []
  const next = checked ? [...current, value] : current.filter((entry) => entry !== value)
  emit('update:modelValue', { ...selected.value, [groupKey]: next })
}
</script>

<template>
  <div class="venue-filters" aria-label="Venue filters">
    <fieldset v-for="(group, groupIndex) in groups" :key="group.key" class="venue-filter-group">
      <legend class="venue-filter-title">{{ group.title }}</legend>

      <div class="venue-filter-options">
        <label v-for="option in group.options" :key="option.value" class="venue-filter-option">
          <input
            type="checkbox"
            :value="option.value"
            :checked="isChecked(group.key, option.value)"
            @change="toggle(group.key, option.value, $event.target.checked)"
          />
          <span class="venue-filter-checkbox" aria-hidden="true" />
          <span>{{ option.label }}</span>
        </label>
      </div>

      <div v-if="groupIndex < groups.length - 1" class="venue-filter-divider" aria-hidden="true" />
    </fieldset>

    <p v-if="!groups.length" class="venue-filter-empty">No filters yet.</p>
  </div>
</template>
