import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { MotifDefs } from './components/Lemons'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* the lemon branch is defined once and referenced everywhere */}
    <MotifDefs />
    <App />
  </StrictMode>,
)
