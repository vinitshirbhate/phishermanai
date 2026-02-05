"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  Home,
  Phone,
  MessageSquare,
  FileAudio,
  ChevronLeft,
  ChevronRight,
  Menu,
  Shield,
} from "lucide-react";

interface SidebarProps {
  activeComponent: string;
  onComponentChange: (component: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

const navigationItems = [
  {
    id: "landing",
    label: "Home",
    icon: Home,
    description: "Landing page",
  },
  {
    id: "voice-call",
    label: "Voice Call",
    icon: Phone,
    description: "Real-time voice analysis",
  },
  {
    id: "sms-email",
    label: "SMS & Email",
    icon: MessageSquare,
    description: "Text message analysis",
  },
  {
    id: "audio-video",
    label: "Audio/Video",
    icon: FileAudio,
    description: "File transcription & analysis",
  },
  {
    id: "llm-honeypot",
    label: "LLM Honeypot",
    icon: Shield,
    description: "Malicious LLM vs Honeypot",
  },
];

export function Sidebar({
  activeComponent,
  onComponentChange,
  isCollapsed,
  onToggleCollapse,
}: SidebarProps) {
  return (
    <motion.div
      className={`bg-midnight-blue-light/30 border-r-2 border-blue-400/30 flex flex-col transition-all duration-300 shadow-xl shadow-blue-400/10 ${
        isCollapsed ? "w-16" : "w-64"
      }`}
      initial={{ x: -300 }}
      animate={{ x: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header */}
      <div className="p-4 border-b-2 border-blue-400/30 bg-midnight-blue-light/20">
        <div className="flex items-center justify-between">
          {!isCollapsed && (
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-electric-cyan rounded-lg flex items-center justify-center">
                <span className="text-midnight-blue font-bold text-sm">P</span>
              </div>
              <span className="text-lg font-bold text-off-white">
                Phisherman AI
              </span>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleCollapse}
            className="text-off-white/70 hover:text-off-white hover:bg-midnight-blue-light/50"
          >
            {isCollapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <div className="space-y-4">
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeComponent === item.id;

            return (
              <motion.button
                key={item.id}
                onClick={() => onComponentChange(item.id)}
                className={`w-full flex items-center space-x-3 px-3 py-3 rounded-lg transition-all duration-200 border ${
                  isActive
                    ? "bg-electric-cyan text-midnight-blue border-electric-cyan shadow-lg shadow-electric-cyan/20"
                    : "text-off-white/70 hover:text-off-white hover:bg-midnight-blue-light/50 border-transparent hover:border-blue-400/40"
                }`}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Icon
                  className={`w-5 h-5 ${
                    isActive ? "text-midnight-blue" : "text-electric-cyan"
                  }`}
                />
                {!isCollapsed && (
                  <div className="flex-1 text-left">
                    <div className="font-medium">{item.label}</div>
                    <div
                      className={`text-xs ${
                        isActive ? "text-midnight-blue/70" : "text-off-white/50"
                      }`}
                    >
                      {item.description}
                    </div>
                  </div>
                )}
              </motion.button>
            );
          })}
        </div>
      </nav>

      {/* Footer */}
      {!isCollapsed && (
        <div className="p-4 border-t-2 border-blue-400/30 bg-midnight-blue-light/20">
          <div className="text-xs text-off-white/50 text-center">
            Phisherman AI v1.0
          </div>
        </div>
      )}
    </motion.div>
  );
}