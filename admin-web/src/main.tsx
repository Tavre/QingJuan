import React from "react";
import ReactDOM from "react-dom/client";
import "antd/dist/reset.css";

import { QingjuanAdmin } from "./App";
import "./styles.css";
import { AdminThemeProvider, initializeThemeMode } from "./theme";

const initialThemeMode = initializeThemeMode();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AdminThemeProvider initialMode={initialThemeMode}>
      <QingjuanAdmin />
    </AdminThemeProvider>
  </React.StrictMode>,
);
