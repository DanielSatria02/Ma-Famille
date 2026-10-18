<script setup>
import { computed, ref, watch } from 'vue'
import {
  errorDetail,
  fetchVenues,
  removeCourtPhoto,
  removeVenuePhoto,
  updateCourt,
  updateVenue,
  uploadCourtPhoto,
  uploadVenuePhoto,
} from '../services/api.js'
import { initialOf, resolveImage } from '../utils/image.js'
import '../styles/photo-settings.css'

const props = defineProps({
  // Bookable facilities (courts) of the active venue, from the venues store.
  facilities: { type: Array, default: () => [] },
  venuePublicId: { type: String, default: '' },
})

const venue = ref(null)
const busy = ref('')
const links = ref({})
const notice = ref('')
const error = ref('')

const courts = computed(() => props.facilities.filter((entry) => entry.kind !== 'cafe'))

async function loadVenue() {
  if (!props.venuePublicId) return
  try {
    const rows = await fetchVenues()
    venue.value = rows.find((row) => row.public_id === props.venuePublicId) ?? null
    links.value = { [props.venuePublicId]: venue.value?.image_url ?? '' }
  } catch (err) {
    error.value = errorDetail(err, 'Could not load the venue.')
  }
}

// The file input is the browser's; we never upload anything unasked.
async function upload(kind, id, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  busy.value = id
  notice.value = ''
  error.value = ''
  try {
    if (kind === 'venue') {
      const updated = await uploadVenuePhoto(id, file)
      venue.value = updated
      links.value[id] = updated.image_url ?? ''
    } else {
      const updated = await uploadCourtPhoto(id, file)
      replaceCourt(updated)
    }
    notice.value = `${file.name} uploaded.`
  } catch (err) {
    error.value = errorDetail(err, 'Could not upload the photo.')
  } finally {
    busy.value = ''
  }
}

async function remove(kind, id) {
  busy.value = id
  notice.value = ''
  error.value = ''
  try {
    if (kind === 'venue') {
      await removeVenuePhoto(id)
      venue.value = { ...venue.value, image_url: null }
      links.value[id] = ''
    } else {
      await removeCourtPhoto(id)
      replaceCourt({ public_id: id, image_url: null })
    }
    notice.value = 'Photo removed.'
  } catch (err) {
    error.value = errorDetail(err, 'Could not remove the photo.')
  } finally {
    busy.value = ''
  }
}

async function saveLink(kind, id) {
  busy.value = `${id}-link`
  notice.value = ''
  error.value = ''
  try {
    const value = (links.value[id] ?? '').trim()
    if (kind === 'venue') {
      venue.value = await updateVenue(id, { image_url: value })
      links.value[id] = venue.value.image_url ?? ''
    } else {
      replaceCourt(await updateCourt(id, { image_url: value }))
    }
    notice.value = value ? 'Link saved.' : 'Link cleared.'
  } catch (err) {
    error.value = errorDetail(err, 'Could not save the link.')
  } finally {
    busy.value = ''
  }
}

function replaceCourt(updated) {
  const target = props.facilities.find((entry) => entry.public_id === updated.public_id)
  if (target) target.image_url = updated.image_url ?? null
  links.value[updated.public_id] = updated.image_url ?? ''
}

// The dashboard hands over the venues store data asynchronously: react to it
// instead of reading it once on mount, or the venue row never appears.
watch(
  () => props.venuePublicId,
  async (id) => {
    if (id) await loadVenue()
  },
  { immediate: true },
)

watch(
  courts,
  (rows) => {
    for (const court of rows) {
      if (!(court.public_id in links.value)) {
        links.value[court.public_id] = court.image_url ?? ''
      }
    }
  },
  { immediate: true, deep: true },
)
</script>

<template>
  <section class="photos" aria-labelledby="photos-title">
    <h2 id="photos-title" class="photos-title">Photos</h2>
    <p class="photos-line">
      PNG, JPEG, GIF or WebP up to 500 kB. One photo per venue and per facility: uploading
      again replaces the old one. A pasted link works too.
    </p>

    <ul class="photo-list">
      <li v-if="venue" class="photo-item">
        <div class="photo-frame">
          <img
            v-if="resolveImage(venue.image_url)"
            :src="resolveImage(venue.image_url)"
            :alt="venue.name"
            class="photo-img"
          />
          <span v-else class="photo-empty" aria-hidden="true">{{ initialOf(venue.name) }}</span>
        </div>
        <div class="photo-body">
          <p class="photo-name">{{ venue.name }}</p>
          <p class="photo-kind">Venue cover</p>
          <div class="photo-row">
            <label class="photo-button">
              {{ busy === venue.public_id ? 'Uploading…' : 'Upload' }}
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                :disabled="Boolean(busy)"
                @change="upload('venue', venue.public_id, $event)"
              />
            </label>
            <button
              type="button"
              class="photo-remove"
              :disabled="Boolean(busy) || !venue.image_url"
              @click="remove('venue', venue.public_id)"
            >
              Remove
            </button>
          </div>
          <div class="photo-row">
            <input
              v-model="links[venue.public_id]"
              type="url"
              placeholder="https://…/photo.jpg"
              class="photo-input"
            />
            <button
              type="button"
              class="photo-save"
              :disabled="Boolean(busy)"
              @click="saveLink('venue', venue.public_id)"
            >
              Save link
            </button>
          </div>
        </div>
      </li>

      <li v-for="court in courts" :key="court.public_id" class="photo-item">
        <div class="photo-frame">
          <img
            v-if="resolveImage(court.image_url)"
            :src="resolveImage(court.image_url)"
            :alt="court.name"
            class="photo-img"
          />
          <span v-else class="photo-empty" aria-hidden="true">{{ initialOf(court.name) }}</span>
        </div>
        <div class="photo-body">
          <p class="photo-name">{{ court.name }}</p>
          <p class="photo-kind">{{ court.sport }} facility</p>
          <div class="photo-row">
            <label class="photo-button">
              {{ busy === court.public_id ? 'Uploading…' : 'Upload' }}
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                :disabled="Boolean(busy)"
                @change="upload('court', court.public_id, $event)"
              />
            </label>
            <button
              type="button"
              class="photo-remove"
              :disabled="Boolean(busy) || !court.image_url"
              @click="remove('court', court.public_id)"
            >
              Remove
            </button>
          </div>
          <div class="photo-row">
            <input
              v-model="links[court.public_id]"
              type="url"
              placeholder="https://…/photo.jpg"
              class="photo-input"
            />
            <button
              type="button"
              class="photo-save"
              :disabled="Boolean(busy)"
              @click="saveLink('court', court.public_id)"
            >
              Save link
            </button>
          </div>
        </div>
      </li>
    </ul>

    <p v-if="notice" class="photos-line" role="status">{{ notice }}</p>
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
  </section>
</template>
