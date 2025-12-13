export interface ChatMessage {
  id: string;
  text: string;
  sender: 'user' | 'assistant';
}
