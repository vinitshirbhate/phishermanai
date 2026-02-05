"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";

interface HeaderProps {
  onNavigateToAudioVideo?: () => void;
}

export function Header({ onNavigateToAudioVideo }: HeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-midnight-blue/95 backdrop-blur-sm border-b border-gray-800">
      <nav className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-electric-cyan rounded-lg flex items-center justify-center">
              <span className="text-midnight-blue font-bold text-sm">P</span>
            </div>
            <span className="text-xl font-bold text-off-white">
              Phisherman AI
            </span>
          </div>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-6">
            <a
              href="#docs"
              className="text-off-white/70 hover:text-off-white transition-colors duration-200"
              aria-label="View documentation"
            >
              Docs
            </a>
            {onNavigateToAudioVideo && (
              <Button
                variant="outline"
                size="sm"
                onClick={onNavigateToAudioVideo}
                className="text-electric-cyan border-electric-cyan hover:bg-electric-cyan hover:text-midnight-blue"
                aria-label="Explore features"
              >
                Explore Features
              </Button>
            )}
            <Button variant="default" size="sm" aria-label="Request a demo">
              Request Demo
            </Button>
          </div>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden text-off-white hover:text-electric-cyan transition-colors duration-200"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={isMenuOpen}
          >
            {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <div className="md:hidden mt-4 py-4 border-t border-gray-800">
            <div className="flex flex-col space-y-4">
              <a
                href="#docs"
                className="text-off-white/70 hover:text-off-white transition-colors duration-200"
                onClick={() => setIsMenuOpen(false)}
              >
                Docs
              </a>
              {onNavigateToAudioVideo && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    onNavigateToAudioVideo();
                    setIsMenuOpen(false);
                  }}
                  className="w-fit text-electric-cyan border-electric-cyan hover:bg-electric-cyan hover:text-midnight-blue"
                >
                  Explore Features
                </Button>
              )}
              <Button
                variant="default"
                size="sm"
                className="w-fit"
                onClick={() => setIsMenuOpen(false)}
              >
                Request Demo
              </Button>
            </div>
          </div>
        )}
      </nav>
    </header>
  );
}
