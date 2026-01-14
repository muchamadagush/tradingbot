// File: frontend/src/hooks/useWebSocket.js
/**
 * Custom hook for WebSocket connection with auto-reconnect and fallback
 */

import { useEffect, useRef, useState, useCallback } from 'react'

const RECONNECT_DELAY = 3000  // 3 seconds
const MAX_RECONNECT_ATTEMPTS = 5
const PING_INTERVAL = 25000   // 25 seconds

export function useWebSocket(url, onMessage, options = {}) {
  const [isConnected, setIsConnected] = useState(false)
  const [connectionState, setConnectionState] = useState('disconnected')
  const wsRef = useRef(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimeout = useRef(null)
  const pingInterval = useRef(null)
  const { fallbackPolling = true, pollingInterval = 2000 } = options
  
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }
    
    setConnectionState('connecting')
    
    try {
      wsRef.current = new WebSocket(url)
      
      wsRef.current.onopen = () => {
        console.log('[WS] Connected')
        setIsConnected(true)
        setConnectionState('connected')
        reconnectAttempts.current = 0
        
        // Start ping interval
        pingInterval.current = setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send('ping')
          }
        }, PING_INTERVAL)
      }
      
      wsRef.current.onmessage = (event) => {
        try {
          // Handle pong
          if (event.data === 'pong') return
          
          const data = JSON.parse(event.data)
          
          // Handle ping from server
          if (data.type === 'ping') return
          
          onMessage?.(data)
        } catch (e) {
          console.error('[WS] Parse error:', e)
        }
      }
      
      wsRef.current.onerror = (error) => {
        console.error('[WS] Error:', error)
      }
      
      wsRef.current.onclose = (event) => {
        console.log('[WS] Disconnected:', event.code, event.reason)
        setIsConnected(false)
        setConnectionState('disconnected')
        
        // Clear ping interval
        if (pingInterval.current) {
          clearInterval(pingInterval.current)
          pingInterval.current = null
        }
        
        // Attempt reconnect
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++
          console.log(`[WS] Reconnecting... (attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS})`)
          setConnectionState('reconnecting')
          
          reconnectTimeout.current = setTimeout(() => {
            connect()
          }, RECONNECT_DELAY * reconnectAttempts.current)
        } else {
          console.log('[WS] Max reconnect attempts reached, falling back to polling')
          setConnectionState('fallback')
        }
      }
    } catch (error) {
      console.error('[WS] Connection error:', error)
      setConnectionState('fallback')
    }
  }, [url, onMessage])
  
  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current)
      reconnectTimeout.current = null
    }
    
    if (pingInterval.current) {
      clearInterval(pingInterval.current)
      pingInterval.current = null
    }
    
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    
    setIsConnected(false)
    setConnectionState('disconnected')
  }, [])
  
  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
      return true
    }
    return false
  }, [])
  
  useEffect(() => {
    connect()
    
    return () => {
      disconnect()
    }
  }, [connect, disconnect])
  
  return {
    isConnected,
    connectionState,
    send,
    reconnect: connect,
    shouldUseFallback: fallbackPolling && (connectionState === 'fallback' || connectionState === 'disconnected'),
  }
}

export default useWebSocket
