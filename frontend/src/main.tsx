import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntApp } from "antd";
import frFR from "antd/locale/fr_FR";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={frFR}
        theme={{
          token: {
            // Brand
            colorPrimary:        '#1b3a6b',
            colorLink:           '#1b3a6b',
            colorLinkHover:      '#2d5fa6',

            // Surfaces
            colorBgContainer:    '#ffffff',
            colorBgLayout:       '#f0f4f8',
            colorBgElevated:     '#ffffff',

            // Typography
            fontFamily:          "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            fontSize:            14,
            colorText:           '#1e2d45',
            colorTextSecondary:  '#6b87b0',
            colorTextTertiary:   '#8097b8',
            colorTextQuaternary: '#b0bdd4',

            // Borders
            borderRadius:        8,
            colorBorder:         '#d0d9e8',
            colorBorderSecondary:'#e8edf5',

            // Shadows
            boxShadow:           '0 1px 3px rgba(27,58,107,0.05), 0 4px 16px rgba(27,58,107,0.06)',
            boxShadowSecondary:  '0 1px 4px rgba(27,58,107,0.05)',
          },
          components: {
            Button: {
              borderRadius:            8,
              controlHeight:           40,
              paddingContentHorizontal:18,
              fontWeight:              600,
              primaryShadow:           '0 2px 8px rgba(27,58,107,0.22)',
              defaultBorderColor:      '#d0d9e8',
              defaultColor:            '#1e2d45',
            },
            Input: {
              borderRadius:     8,
              controlHeight:    44,
              paddingBlock:     10,
              paddingInline:    14,
              activeBorderColor:'#1b3a6b',
              hoverBorderColor: '#4a7bc8',
            },
            Select: {
              borderRadius:  8,
              controlHeight: 44,
            },
            Table: {
              borderRadius:        8,
              headerBg:            '#f5f8fc',
              headerColor:         '#8097b8',
              headerSortActiveBg:  '#f0f4f8',
              rowHoverBg:          '#f8fafd',
              borderColor:         '#f0f4f8',
              cellPaddingBlock:    13,
              cellPaddingInline:   16,
            },
            Modal: {
              borderRadius:             16,
              paddingContentHorizontal: 28,
              titleFontSize:            17,
            },
            Form: {
              itemMarginBottom: 20,
              labelFontSize:    13,
            },
            Tag: {
              borderRadius: 20,
              fontSize:     12,
            },
            Tooltip: {
              borderRadius:    8,
              colorBgSpotlight:'#1e2d45',
              paddingXS:       8,
            },
            Dropdown: {
              borderRadius: 10,
            },
            Card: {
              borderRadius: 14,
            },
            Popconfirm: {
              borderRadius: 10,
            },
            Spin: {
              colorPrimary: '#1b3a6b',
            },
          },
        }}
      >
        <AntApp>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
