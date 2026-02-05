"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Play, Download, AlertTriangle } from "lucide-react";

export function DemoCard() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const handleDemo = () => {
    setIsAnalyzing(true);
    setTimeout(() => {
      setIsAnalyzing(false);
      setShowResults(true);
    }, 2000);
  };

  const handleGenerateReport = () => {
    // Mock report generation
    alert("Forensic report generated! (Demo only)");
  };

  return (
    <section className="py-20 bg-midnight-blue-light/30">
      <div className="container mx-auto px-4">
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
        >
          <h2 className="text-3xl md:text-4xl font-bold text-off-white mb-4">
            Live Demo Snapshot
          </h2>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            Live demo pipeline — paste sample message. See detection score,
            honeypot reply, and forensic PDF.
          </p>
        </motion.div>

        <div className="max-w-4xl mx-auto">
          <Card className="bg-midnight-blue-light/50 backdrop-blur-sm border-gray-700">
            <CardHeader>
              <CardTitle className="text-off-white text-center">
                Phishing Detection Demo
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Sample Message */}
              <div className="bg-midnight-blue/50 rounded-lg p-4 border border-gray-600">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4 text-sunset-orange" />
                  <span className="text-sm font-medium text-off-white">
                    Sample Message
                  </span>
                </div>
                <p className="text-off-white/80 text-sm italic">
                  "Urgent: Your account will be suspended in 24 hours. Click
                  here to verify your identity immediately."
                </p>
              </div>

              {/* Detection Score */}
              {showResults && (
                <motion.div
                  className="space-y-4"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5 }}
                >
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-sm font-medium text-off-white">
                        Detection Score
                      </span>
                      <span className="text-sm font-bold text-sunset-orange">
                        87%
                      </span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                      <motion.div
                        className="bg-gradient-to-r from-sunset-orange to-red-500 h-2 rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: "87%" }}
                        transition={{ duration: 1, delay: 0.5 }}
                      />
                    </div>
                  </div>

                  {/* Honeypot Status */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-off-white">
                      Status
                    </span>
                    <Badge variant="warning">Honeypot Diverted</Badge>
                  </div>

                  {/* Generated Reply */}
                  <div className="bg-midnight-blue/50 rounded-lg p-4 border border-gray-600">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-2 h-2 bg-electric-cyan rounded-full" />
                      <span className="text-sm font-medium text-electric-cyan">
                        Honeypot Reply
                      </span>
                    </div>
                    <p className="text-off-white/80 text-sm">
                      "Thank you for the notification. I'll verify my account
                      details right away."
                    </p>
                  </div>
                </motion.div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Button
                  onClick={handleDemo}
                  disabled={isAnalyzing}
                  className="flex items-center gap-2"
                >
                  {isAnalyzing ? (
                    <>
                      <motion.div
                        className="w-4 h-4 border-2 border-midnight-blue border-t-electric-cyan rounded-full"
                        animate={{ rotate: 360 }}
                        transition={{
                          duration: 1,
                          repeat: Infinity,
                          ease: "linear",
                        }}
                      />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Open Demo
                    </>
                  )}
                </Button>

                {showResults && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Button
                      variant="outline"
                      onClick={handleGenerateReport}
                      className="flex items-center gap-2"
                    >
                      <Download className="w-4 h-4" />
                      Generate Report
                    </Button>
                  </motion.div>
                )}
              </div>

              {/* Demo Notice */}
              <div className="text-center">
                <p className="text-xs text-off-white/50">
                  This is a demonstration. No actual phishing detection is
                  performed.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
