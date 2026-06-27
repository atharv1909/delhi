import { useState, useRef, useCallback } from 'react'
import { Mic, MicOff, Loader } from 'lucide-react'

interface VoiceInputProps {
  onTranscript: (text: string) => void
  disabled?: boolean
}

const SMALLEST_API_KEY = 'sk_9b38c60e7ed18cc43da64dc9322c97fe'
const WS_URL = `wss://api.smallest.ai/waves/v1/pulse/get_text?language=en&encoding=linear16&sample_rate=16000&word_timestamps=true`

export default function VoiceInput({ onTranscript, disabled }: VoiceInputProps) {
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } })
      
      // Try Smallest AI WebSocket first
      try {
        const ws = new WebSocket(WS_URL, [])
        ws.binaryType = 'arraybuffer'
        
        // Add auth header via protocol (WebSocket doesn't support headers in browser)
        // Fallback to browser SpeechRecognition if WebSocket fails
        wsRef.current = ws
        
        ws.onopen = () => {
          // Send auth
          ws.send(JSON.stringify({ type: 'auth', token: SMALLEST_API_KEY }))
        }
        
        ws.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data)
            if (data.transcript && data.is_final) {
              onTranscript(data.transcript)
              setProcessing(false)
            }
          } catch {}
        }
        
        ws.onerror = () => {
          // Fallback to browser speech recognition
          useBrowserSpeechRecognition()
        }
      } catch {
        useBrowserSpeechRecognition()
      }

      // Record audio chunks
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRef.current = mediaRecorder
      chunksRef.current = []
      
      mediaRecorder.ondataavailable = async (e) => {
        if (e.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          const arrayBuffer = await e.data.arrayBuffer()
          wsRef.current.send(arrayBuffer)
        }
        chunksRef.current.push(e.data)
      }

      mediaRecorder.start(250) // Send chunks every 250ms
      setRecording(true)
    } catch (err) {
      console.error('Microphone access denied:', err)
      useBrowserSpeechRecognition()
    }
  }, [onTranscript])

  const stopRecording = useCallback(() => {
    setRecording(false)
    setProcessing(true)
    
    if (mediaRef.current && mediaRef.current.state !== 'inactive') {
      mediaRef.current.stop()
      mediaRef.current.stream.getTracks().forEach(t => t.stop())
    }
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'finalize' }))
      setTimeout(() => {
        wsRef.current?.close()
        setProcessing(false)
      }, 3000)
    } else {
      setProcessing(false)
    }
  }, [])

  const useBrowserSpeechRecognition = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser.')
      setRecording(false)
      return
    }
    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-IN'

    let fullText = ''
    recognition.onresult = (event: any) => {
      let transcript = ''
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript
      }
      fullText = transcript
    }
    recognition.onend = () => {
      if (fullText) onTranscript(fullText)
      setRecording(false)
      setProcessing(false)
    }
    recognition.onerror = () => {
      setRecording(false)
      setProcessing(false)
    }
    recognition.start()
    setRecording(true)

    // Auto-stop after 15 seconds
    setTimeout(() => {
      try { recognition.stop() } catch {}
    }, 15000)
  }

  const handleClick = () => {
    if (disabled || processing) return
    if (recording) {
      stopRecording()
    } else {
      startRecording()
    }
  }

  return (
    <button
      className={`voice-btn ${recording ? 'recording' : ''}`}
      onClick={handleClick}
      disabled={disabled || processing}
      title={recording ? 'Stop recording' : 'Speak your investment goal'}
    >
      {processing ? <Loader size={16} className="spin" /> : recording ? <MicOff size={16} /> : <Mic size={16} />}
    </button>
  )
}
