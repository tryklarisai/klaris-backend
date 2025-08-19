import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import ThemeProvider from "./theme/ThemeProvider";
import SnackbarProvider from "./ui/SnackbarProvider";
import RegisterPage from "./pages/RegisterPage";
import LoginPage from "./pages/LoginPage";
import DashboardLayout from "./pages/DashboardLayout";
import DashboardPage from "./pages/DashboardPage";
import ConnectorsPage from "./pages/ConnectorsPage";
import ConnectorDetailPage from "./pages/ConnectorDetailPage";
import DataRelationshipsPage from "./pages/DataRelationshipsPage";
import BusinessContextPage from "./pages/BusinessContextPage";
import ChatPage from "./pages/ChatPage";

function App() {
  return (
    <ThemeProvider>
      <SnackbarProvider>
        <Router>
          <Routes>
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<DashboardLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="connectors" element={<ConnectorsPage />} />
              <Route path="connectors/:connectorId" element={<ConnectorDetailPage />} />
              <Route path="relationships" element={<DataRelationshipsPage />} />
              <Route path="business-context" element={<BusinessContextPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:threadId" element={<ChatPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Router>
      </SnackbarProvider>
    </ThemeProvider>
  );
}

export default App;
