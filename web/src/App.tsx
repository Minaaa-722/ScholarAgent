import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ResearchCreation from "./pages/ResearchCreation";
import AgentExecution from "./pages/AgentExecution";
import KnowledgeExplorer from "./pages/KnowledgeExplorer";
import FinalReview from "./pages/FinalReview";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import { ToastProvider } from "./components/Toast";

function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <ToastProvider>
          <Layout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/create" element={<ResearchCreation />} />
              <Route path="/execution" element={<AgentExecution />} />
              <Route path="/explorer" element={<KnowledgeExplorer />} />
              <Route path="/review" element={<FinalReview />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </Layout>
        </ToastProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
export default App;