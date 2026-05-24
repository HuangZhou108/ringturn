import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './i18n'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
    // StrictMode temporarily disabled for debugging
    // <StrictMode>
        <BrowserRouter>
            <App />
        </BrowserRouter>
    // </StrictMode>,
)