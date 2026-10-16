<script setup>
import { computed, reactive, ref, watch } from 'vue'
import '../styles/opening-schedule.css'

// schedule: [{ day, start, end }] with "HH:MM" times; emits `update` with the changed entry.
const props = defineProps({
  schedule: { type: Array, required: true },
})

const emit = defineEmits(['update'])

const pad = (value) => String(value).padStart(2, '0')
const hours = Array.from({ length: 24 }, (_, hour) => pad(hour))
const minutes = Array.from({ length: 60 }, (_, minute) => pad(minute))

const selectedDay = ref(props.schedule[0]?.day ?? '')
const form = reactive({ startHour: '00', startMinute: '00', endHour: '00', endMinute: '00' })
const saved = ref(false)

const days = computed(() => props.schedule.map((entry) => entry.day))

const startTime = computed(() => `${form.startHour}:${form.startMinute}`)
const endTime = computed(() => `${form.endHour}:${form.endMinute}`)
const isValid = computed(() => startTime.value < endTime.value)

function loadDay() {
  const entry = props.schedule.find((item) => item.day === selectedDay.value)
  if (!entry) return
  ;[form.startHour, form.startMinute] = entry.start.split(':')
  ;[form.endHour, form.endMinute] = entry.end.split(':')
}

function save() {
  if (!isValid.value) return
  emit('update', { day: selectedDay.value, start: startTime.value, end: endTime.value })
  saved.value = true
}

watch(selectedDay, () => {
  saved.value = false
  loadDay()
}, { immediate: true })
</script>

<template>
  <section class="opening" aria-labelledby="opening-title">
    <h2 id="opening-title" class="opening-title">Opening & Closing Schedule</h2>

    <div class="opening-layout">
      <ul class="opening-list">
        <li v-for="entry in schedule" :key="entry.day" class="opening-card">
          <p class="opening-day">{{ entry.day }}</p>
          <p class="opening-time">START: {{ entry.start }}</p>
          <p class="opening-time">END: {{ entry.end }}</p>
        </li>
      </ul>

      <form class="opening-editor" @submit.prevent="save">
        <h3 class="opening-editor-title">Edit schedule</h3>

        <label class="opening-field">
          <span class="opening-label">Day</span>
          <select v-model="selectedDay" class="opening-select">
            <option v-for="day in days" :key="day" :value="day">{{ day }}</option>
          </select>
        </label>

        <fieldset class="opening-field">
          <legend class="opening-label">Start</legend>
          <div class="opening-time-picker">
            <select v-model="form.startHour" class="opening-select" aria-label="Start hour" @change="saved = false">
              <option v-for="hour in hours" :key="hour" :value="hour">{{ hour }}</option>
            </select>
            <span aria-hidden="true">:</span>
            <select v-model="form.startMinute" class="opening-select" aria-label="Start minute" @change="saved = false">
              <option v-for="minute in minutes" :key="minute" :value="minute">{{ minute }}</option>
            </select>
          </div>
        </fieldset>

        <fieldset class="opening-field">
          <legend class="opening-label">End</legend>
          <div class="opening-time-picker">
            <select v-model="form.endHour" class="opening-select" aria-label="End hour" @change="saved = false">
              <option v-for="hour in hours" :key="hour" :value="hour">{{ hour }}</option>
            </select>
            <span aria-hidden="true">:</span>
            <select v-model="form.endMinute" class="opening-select" aria-label="End minute" @change="saved = false">
              <option v-for="minute in minutes" :key="minute" :value="minute">{{ minute }}</option>
            </select>
          </div>
        </fieldset>

        <p v-if="!isValid" class="opening-error" role="alert">End time must be after start time.</p>
        <p v-else-if="saved" class="opening-success" role="status">Schedule updated.</p>

        <button type="submit" class="opening-save" :disabled="!isValid">Save</button>
      </form>
    </div>
  </section>
</template>
