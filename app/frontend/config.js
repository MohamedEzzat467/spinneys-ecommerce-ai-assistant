/**
 * Spinneys E-Commerce Store & AI Assistant — Cloud Environment Configuration
 * 
 * In unified deployment (FastAPI serving both backend and frontend):
 * Relative paths ("") ensure all API requests route directly to the same host domain.
 * If hosting frontend separately on external CDN/Vercel:
 * Set window.__SPINNEYS_API_BASE__ = "https://spinneys-assistant.onrender.com";
 */
window.__SPINNEYS_API_BASE__ = window.__SPINNEYS_API_BASE__ || "";
