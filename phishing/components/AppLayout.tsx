"use client";

import { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { LandingPage } from "@/components/LandingPage";
import { VoiceCallComponent } from "@/components/VoiceCallComponent";
import { SMSEmailComponent } from "@/components/SMSEmailComponent";
import AudioVideoPage from "@/app/audio_video/page";
import LLMHoneypotPage from "@/app/llm_honeypot/page";

export function AppLayout() {
  const [activeComponent, setActiveComponent] = useState("landing");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const renderActiveComponent = () => {
    switch (activeComponent) {
      case "landing":
        return <LandingPage />;
      case "voice-call":
        return <VoiceCallComponent />;
      case "sms-email":
        return <SMSEmailComponent />;
      case "audio-video":
        return <AudioVideoPage />;
      case "llm-honeypot":
        return <LLMHoneypotPage />;
      default:
        return <LandingPage />;
    }
  };

  return (
    <div className="min-h-screen bg-midnight-blue">
      {/* Header */}
      <Header
        onNavigateToAudioVideo={() => setActiveComponent("audio-video")}
      />

      {/* Conditional Layout */}
      {activeComponent === "landing" ? (
        // Landing page without sidebar
        <div className="pt-16">{renderActiveComponent()}</div>
      ) : (
        // Other pages with sidebar
        <div className="flex pt-16">
          {/* Sidebar */}
          <Sidebar
            activeComponent={activeComponent}
            onComponentChange={setActiveComponent}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          />

          {/* Main Content */}
          <div
            className={`flex-1 transition-all duration-300 ${
              isSidebarCollapsed ? "ml-0" : "ml-0"
            }`}
          >
            {renderActiveComponent()}
          </div>
        </div>
      )}
    </div>
  );
}
