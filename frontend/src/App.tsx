import { Routes, Route } from 'react-router-dom'
import Home from './pages/home.tsx'
import ChatFlow from './pages/ChatFlow.tsx'

function App() {
  return (
      <Routes>
        <Route path="/" element={<Home />} />
        {/* 支持2种模式：/chat 新建会话，/chat/conversation/:id */}
        <Route path="/chat" element={<ChatFlow />} />
        <Route path="/chat/c/:conversationId" element={<ChatFlow />} />
      </Routes>
  )
}

export default App
