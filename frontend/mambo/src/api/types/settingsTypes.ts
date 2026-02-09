// frontend/mambo/src/api/types/settingsTypes.ts

export interface GlobalSettingsUpdate {
  default_model_id: string | null
  title_generation_model_id: string | null
  last_selected_provider_id: string | null
  default_max_context_messages: number | null
  default_temperature: number | null
  default_top_p: number | null
  default_stream: boolean | null
  proxy_enabled: boolean | null
  proxy_url: string | null
  user_avatar_url: string | null
  ai_avatar_url: string | null
  zip_history_system_prompt?: string | null
  frontend_editor: string | null
  kb_default_chunk_size: number | null
  kb_default_chunk_overlap: number | null
  send_message_shortcut: string | null
}

export interface ProxyTestRequest {
  proxy_url: string
  test_url: string
}
