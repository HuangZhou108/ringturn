import { Routes, Route } from 'react-router-dom'
import Home from './pages/home.tsx'
import ChatFlow from './pages/ChatFlow.tsx'

function App() {
  return (
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/chat" element={<ChatFlow />} />
      </Routes>
  )
}

export default App
