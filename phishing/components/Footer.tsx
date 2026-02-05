"use client";

import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { FileText, Shield, Mail } from "lucide-react";

export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-midnight-blue-light/50 border-t border-gray-800">
      <div className="container mx-auto px-4 py-12">
        <div className="grid md:grid-cols-4 gap-8">
          {/* Logo and Description */}
          <motion.div
            className="md:col-span-2"
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            viewport={{ once: true }}
          >
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 bg-electric-cyan rounded-lg flex items-center justify-center">
                <span className="text-midnight-blue font-bold text-sm">P</span>
              </div>
              <span className="text-xl font-bold text-off-white">
                Phisherman AI
              </span>
            </div>
            <p className="text-off-white/70 text-sm leading-relaxed max-w-md">
              Advanced AI-resistant phishing detection and deception framework.
              Protect your organization from sophisticated multi-channel
              threats.
            </p>
          </motion.div>

          {/* Quick Links */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            viewport={{ once: true }}
          >
            <h3 className="text-off-white font-semibold mb-4">Quick Links</h3>
            <div className="space-y-3">
              <a
                href="#docs"
                className="flex items-center space-x-2 text-off-white/70 hover:text-electric-cyan transition-colors duration-200"
              >
                <FileText className="w-4 h-4" />
                <span>Docs</span>
              </a>
              <a
                href="#privacy"
                className="flex items-center space-x-2 text-off-white/70 hover:text-electric-cyan transition-colors duration-200"
              >
                <Shield className="w-4 h-4" />
                <span>Privacy</span>
              </a>
              <a
                href="#contact"
                className="flex items-center space-x-2 text-off-white/70 hover:text-electric-cyan transition-colors duration-200"
              >
                <Mail className="w-4 h-4" />
                <span>Contact</span>
              </a>
            </div>
          </motion.div>

          {/* CTA */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            viewport={{ once: true }}
          >
            <h3 className="text-off-white font-semibold mb-4">Get Started</h3>
            <Button variant="default" size="sm" className="w-full mb-4">
              Request Demo
            </Button>
            <p className="text-xs text-off-white/50">
              Ready to protect your organization?
            </p>
          </motion.div>
        </div>

        {/* Bottom Bar */}
        <motion.div
          className="mt-12 pt-8 border-t border-gray-800 flex flex-col md:flex-row justify-between items-center"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.6 }}
          viewport={{ once: true }}
        >
          <p className="text-off-white/50 text-sm">
            © {currentYear} Phisherman AI. All rights reserved.
          </p>
          <div className="flex space-x-6 mt-4 md:mt-0">
            <a
              href="#terms"
              className="text-off-white/50 hover:text-off-white text-sm transition-colors duration-200"
            >
              Terms
            </a>
            <a
              href="#security"
              className="text-off-white/50 hover:text-off-white text-sm transition-colors duration-200"
            >
              Security
            </a>
          </div>
        </motion.div>
      </div>
    </footer>
  );
}
