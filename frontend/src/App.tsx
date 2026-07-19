import { Routes, Route } from 'react-router-dom'
import Home from './pages/home.tsx'
import ChatFlow from './pages/ChatFlow.tsx'
import {useEffect, useState} from "react";
import UserManualModal from './components/UserManualModal'

function App() {
    const [manualOpen, setManualOpen] = useState(false)
    useEffect(() => {
        const hasSeenManual = localStorage.getItem('ringturn_has_seen_manual');
        if (!hasSeenManual) {
            setManualOpen(true);
            localStorage.setItem('ringturn_has_seen_manual', 'true');
        }
    }, []);
    return (
        <>
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/chat" element={<ChatFlow />} />
                <Route path="/chat/c/:conversationId" element={<ChatFlow />} />
            </Routes>
            {/* 用户手册弹窗 */}
            <UserManualModal
                isOpen={manualOpen}
                onClose={() => setManualOpen(false)}
            />
        </>
  )
}

export default App
