// File: frontend/src/services/authService.js
/**
 * Authentication service for API requests
 */

const VITE_API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const API_KEY_STORAGE_KEY = 'bot_api_key'
const JWT_TOKEN_STORAGE_KEY = 'bot_jwt_token'

class AuthService {
  constructor() {
    this.apiKey = localStorage.getItem(API_KEY_STORAGE_KEY) || ''
    this.jwtToken = localStorage.getItem(JWT_TOKEN_STORAGE_KEY) || ''
    this.authMode = null
    this.checkAuthStatus()
  }

  async checkAuthStatus() {
    try {
      const response = await fetch(`${VITE_API_URL}/api/auth/status`)
      const data = await response.json()
      this.authMode = data.auth_mode
      this.authEnabled = data.auth_enabled
      return data
    } catch (error) {
      console.error('Failed to check auth status:', error)
      this.authEnabled = false
      return { auth_enabled: false }
    }
  }

  setApiKey(key) {
    this.apiKey = key
    if (key) {
      localStorage.setItem(API_KEY_STORAGE_KEY, key)
    } else {
      localStorage.removeItem(API_KEY_STORAGE_KEY)
    }
  }

  setJwtToken(token) {
    this.jwtToken = token
    if (token) {
      localStorage.setItem(JWT_TOKEN_STORAGE_KEY, token)
    } else {
      localStorage.removeItem(JWT_TOKEN_STORAGE_KEY)
    }
  }

  getApiKey() {
    return this.apiKey
  }

  getJwtToken() {
    return this.jwtToken
  }

  isAuthenticated() {
    return !this.authEnabled || !!this.apiKey || !!this.jwtToken
  }

  getAuthHeaders() {
    const headers = {}
    
    if (this.jwtToken) {
      headers['Authorization'] = `Bearer ${this.jwtToken}`
    } else if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey
    }
    
    return headers
  }

  async login(apiKey) {
    // Try to exchange API key for JWT token
    try {
      const response = await fetch(`${VITE_API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey })
      })
      
      if (response.ok) {
        const data = await response.json()
        this.setJwtToken(data.access_token)
        this.setApiKey(apiKey) // Store API key as fallback
        return { success: true, role: data.role }
      } else if (response.status === 401) {
        return { success: false, error: 'Invalid API key' }
      } else {
        // If JWT login fails, just use API key directly
        this.setApiKey(apiKey)
        return { success: true, fallback: true }
      }
    } catch (error) {
      // Network error, store API key for direct use
      this.setApiKey(apiKey)
      return { success: true, fallback: true }
    }
  }

  logout() {
    this.setApiKey('')
    this.setJwtToken('')
  }

  async getCurrentUser() {
    if (!this.isAuthenticated()) {
      return null
    }
    
    try {
      const response = await fetch(`${VITE_API_URL}/api/auth/me`, {
        headers: this.getAuthHeaders()
      })
      
      if (response.ok) {
        return await response.json()
      }
      return null
    } catch (error) {
      return null
    }
  }
}

export const authService = new AuthService()

// Configure axios to include auth headers
export function configureAxiosAuth(axios) {
  axios.interceptors.request.use((config) => {
    const headers = authService.getAuthHeaders()
    Object.assign(config.headers, headers)
    return config
  })
  
  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        // Token expired or invalid
        authService.logout()
        // Optionally trigger re-login UI
        window.dispatchEvent(new CustomEvent('auth:expired'))
      }
      return Promise.reject(error)
    }
  )
}

export default authService
