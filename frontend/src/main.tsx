import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/global.css";

async function bootstrap() {
  // Install mock API in development when VITE_MOCK_API=true
  if (import.meta.env.VITE_MOCK_API === "true") {
    const { installMockHandler } = await import("./mocks/handler");
    installMockHandler();
  }

  const root = document.getElementById("root");
  if (!root) throw new Error("Root element not found");

  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

bootstrap();
