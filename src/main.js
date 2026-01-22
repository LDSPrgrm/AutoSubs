import { createApp } from 'vue'
import App from './App.vue'

// Vuetify
import 'vuetify/styles'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import '@mdi/font/css/materialdesignicons.css'
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';

const vuetify = createVuetify({
    components,
    directives,
    theme: {
        defaultTheme: 'light',
        themes: {
            light: {
                dark: false,
                colors: {
                    primary: '#FF4B4B',
                    secondary: '#262730',
                    accent: '#FF4B4B',
                    background: '#F0F2F6',
                    surface: '#FFFFFF',
                    'surface-variant': '#F2F2F2',
                    error: '#FF5252',
                    info: '#2196F3',
                    success: '#4CAF50',
                    warning: '#FFC107',
                }
            }
        }
    },
    defaults: {
        VCard: {
            rounded: 'lg',
            elevation: 2,
        },
        VBtn: {
            rounded: 'lg',
            fontWeight: '600',
            letterSpacing: '0.5px'
        },
        VTextField: {
            variant: 'outlined',
            color: 'primary',
            density: 'comfortable',
            rounded: 'lg'
        }
    },
    icons: {
        defaultSet: 'mdi',
        aliases,
        sets: {
            mdi,
        },
    },
})

createApp(App).use(vuetify).mount('#app')
