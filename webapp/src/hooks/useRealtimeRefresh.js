import { useEffect } from 'react'
import { supabase } from '../lib/supabase.js'

export function useRealtimeRefresh(table, onChange) {
  useEffect(() => {
    const channel = supabase
      .channel(`jarvis-${table}-${crypto.randomUUID()}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table },
        () => onChange(),
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [table, onChange])
}
