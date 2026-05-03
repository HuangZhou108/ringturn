import { Routes, Route } from 'react-router-dom'
import ChatFlow0 from './ChatFlow0'
import ChatFlow1 from './ChatFlow1'

function App() {
  return (
      <Routes>
        <Route path="/" element={<ChatFlow0 />} />
        <Route path="/chat" element={<ChatFlow1 />} />
      </Routes>
  )
}

export default App