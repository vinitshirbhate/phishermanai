"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Phone, Mic, MicOff, PhoneOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export function VoiceCallComponent() {
  const [isRecording, setIsRecording] = useState(false);
  const [isCallActive, setIsCallActive] = useState(false);

  return (
    <div className="min-h-screen bg-midnight-blue py-20">
      <div className="container mx-auto px-4">
        <motion.div
          className="text-center mb-12"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <h1 className="text-4xl md:text-5xl font-bold text-off-white mb-4">
            Voice Call Analysis
          </h1>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            Real-time voice call monitoring and phishing detection
          </p>
        </motion.div>

        <div className="max-w-4xl mx-auto">
          <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
            <CardHeader>
              <CardTitle className="text-xl text-off-white flex items-center gap-2">
                <Phone className="w-5 h-5" />
                Voice Call Interface
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="text-center py-12">
                <div className="w-32 h-32 mx-auto mb-6 rounded-full bg-electric-cyan/20 flex items-center justify-center">
                  <Phone className="w-16 h-16 text-electric-cyan" />
                </div>
                <h3 className="text-2xl font-bold text-off-white mb-4">
                  {isCallActive ? "Call in Progress" : "Ready to Monitor"}
                </h3>
                <p className="text-off-white/70 mb-8">
                  {isCallActive
                    ? "Voice call is being monitored for phishing attempts"
                    : "Start a voice call to begin real-time phishing detection"}
                </p>

                <div className="flex justify-center gap-4">
                  <Button
                    onClick={() => setIsCallActive(!isCallActive)}
                    className={`px-8 py-3 font-semibold ${
                      isCallActive
                        ? "bg-red-500 hover:bg-red-600 text-white"
                        : "bg-green-500 hover:bg-green-600 text-white"
                    }`}
                  >
                    {isCallActive ? (
                      <>
                        <PhoneOff className="w-4 h-4 mr-2" />
                        End Call
                      </>
                    ) : (
                      <>
                        <Phone className="w-4 h-4 mr-2" />
                        Start Call
                      </>
                    )}
                  </Button>

                  {isCallActive && (
                    <Button
                      onClick={() => setIsRecording(!isRecording)}
                      className={`px-8 py-3 font-semibold ${
                        isRecording
                          ? "bg-red-500 hover:bg-red-600 text-white"
                          : "bg-electric-cyan text-midnight-blue hover:bg-electric-cyan/90"
                      }`}
                    >
                      {isRecording ? (
                        <>
                          <MicOff className="w-4 h-4 mr-2" />
                          Stop Recording
                        </>
                      ) : (
                        <>
                          <Mic className="w-4 h-4 mr-2" />
                          Start Recording
                        </>
                      )}
                    </Button>
                  )}
                </div>
              </div>

              {isCallActive && (
                <div className="mt-8 p-6 bg-midnight-blue-light/10 rounded-lg">
                  <h4 className="text-lg font-semibold text-off-white mb-4">
                    Real-time Analysis
                  </h4>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-400">
                        SAFE
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Current Status
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-electric-cyan">
                        0%
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Risk Score
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-electric-cyan">
                        0
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Suspicious Phrases
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
