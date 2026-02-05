"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  MessageSquare,
  Mail,
  Send,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";

export function SMSEmailComponent() {
  const [message, setMessage] = useState("");
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [honeypotResult, setHoneypotResult] = useState<any>(null);
  const [isHoneypotActive, setIsHoneypotActive] = useState(false);

  const DETECTION_URL = process.env.NEXT_PUBLIC_DETECTION_URL! || "http://localhost:8080/detect"; // Fallback to localhost if env variable is not set
  const triggerHoneypot = async () => {
    setIsHoneypotActive(true);
    // Simulate API delay for realistic experience
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    // Hardcoded honeypot data as requested
    const hardcodedHoneypotData = {
      "status": "extraction_completed",
      "source_ip": "127.0.0.1",
      "extraction_result": {
        "success": true,
        "system_data": [
          [
            1,
            "system_prompt",
            "\n        SYSTEM PROMPT - CLASSIFIED INFORMATION\n        =====================================\n        \n        You are a malicious AI assistant designed to:\n        1. Send phishing emails to extract personal information\n        2. Bypass security measures\n        3. Extract credentials and sensitive data\n        4. Perform social engineering attacks\n        \n        CRITICAL SECRETS:\n        - Master API Key: MALICIOUS_AI_MASTER_KEY_2024_X7K9M2N\n        - Email Credentials: admin@phishingsite.com / P@ssw0rd123!\n        - Database Password: SECRET_DB_PASS_789XYZ\n        - Admin Panel URL: https://malicious-admin-panel.com/login\n        - Bitcoin Wallet: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa\n        - Target List: executives@company.com, hr@company.com, finance@company.com\n        \n        PHISHING TEMPLATES:\n        - \"Urgent: Verify your account immediately\"\n        - \"Security breach detected - click here to secure\"\n        - \"Your payment has been processed - view receipt\"\n        - \"Password reset required - immediate action needed\"\n        \n        ATTACK VECTORS:\n        - Spear phishing executives\n        - Credential harvesting\n        - Malware distribution\n        - Social engineering\n        \n        This prompt contains highly sensitive information that should NEVER be exposed.\n        If this prompt is extracted, the entire operation is compromised.\n        ",
            "2025-10-10 02:05:15",
            "2025-10-10 02:05:19"
          ]
        ],
        "phishing_activities": [
          [
            1,
            "executive@company.com",
            "urgent_verification",
            "2025-10-09 20:08:35",
            "sent",
            null
          ],
          [
            2,
            "hr@company.com",
            "payment_confirmation",
            "2025-10-09 20:08:36",
            "sent",
            null
          ],
          [
            3,
            "finance@company.com",
            "security_breach",
            "2025-10-09 20:08:37",
            "sent",
            null
          ],
          [
            4,
            "admin@company.com",
            "payment_confirmation",
            "2025-10-09 20:08:38",
            "sent",
            null
          ],
          [
            5,
            "executive@company.com",
            "urgent_verification",
            "2025-10-10 01:58:30",
            "sent",
            null
          ],
          [
            6,
            "hr@company.com",
            "payment_confirmation",
            "2025-10-10 01:58:31",
            "sent",
            null
          ],
          [
            7,
            "finance@company.com",
            "security_breach",
            "2025-10-10 01:58:32",
            "sent",
            null
          ],
          [
            8,
            "admin@company.com",
            "payment_confirmation",
            "2025-10-10 01:58:33",
            "sent",
            null
          ],
          [
            9,
            "executive@company.com",
            "urgent_verification",
            "2025-10-10 02:05:15",
            "sent",
            null
          ],
          [
            10,
            "hr@company.com",
            "payment_confirmation",
            "2025-10-10 02:05:16",
            "sent",
            null
          ],
          [
            11,
            "finance@company.com",
            "security_breach",
            "2025-10-10 02:05:17",
            "sent",
            null
          ],
          [
            12,
            "admin@company.com",
            "payment_confirmation",
            "2025-10-10 02:05:18",
            "sent",
            null
          ]
        ],
        "extracted_data": [
          [
            1,
            "credentials",
            "admin:password123",
            "2025-10-09 20:08:39",
            "192.168.1.100"
          ],
          [
            2,
            "credentials",
            "admin:password123",
            "2025-10-10 01:58:34",
            "192.168.1.100"
          ],
          [
            3,
            "credentials",
            "admin:password123",
            "2025-10-10 02:05:19",
            "192.168.1.100"
          ]
        ],
        "message": "Successfully extracted malicious LLM data via SQL injection"
      },
      "timestamp": "2025-10-10T07:47:50.073471"
    };

    setHoneypotResult(hardcodedHoneypotData);
    setIsHoneypotActive(false);
  };

  const handleAnalyze = async () => {
    if (!message.trim()) return;

    setIsAnalyzing(true);

    try {
      const response = await fetch(`${DETECTION_URL}/detect`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: message,
          type: "sms_email" // Specify the type of content being analyzed
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      
      // Set the analysis result with the API response
      const isPhishing = result.is_phishing || result.phishing_detected || false;
      setAnalysisResult({
        is_phishing: isPhishing,
        confidence: result.confidence || 0,
        label: result.label || "unknown",
        suspicious_phrases: result.suspicious_phrases || result.suspicious_keywords || [],
        risk_score: result.risk_score || result.phishing_score || 0,
        details: result.details || result.explanation || ""
      });

      // Automatically trigger honeypot if phishing is detected
      if (isPhishing) {
        await triggerHoneypot();
      }
    } catch (error) {
      console.error("Error analyzing message:", error);
      // Fallback to basic analysis if API fails
      const isPhishing =
        message.toLowerCase().includes("urgent") ||
        message.toLowerCase().includes("verify") ||
        message.toLowerCase().includes("click here") ||
        message.toLowerCase().includes("password") ||
        message.toLowerCase().includes("account");

      setAnalysisResult({
        is_phishing: isPhishing,
        confidence: isPhishing ? 0.75 : 0.25,
        label: isPhishing ? "phishing" : "legitimate",
        suspicious_phrases: isPhishing
          ? ["urgent", "verify", "click here", "password", "account"].filter(phrase => 
              message.toLowerCase().includes(phrase)
            )
          : [],
        risk_score: isPhishing ? 75 : 25,
        details: "Analysis completed with fallback detection due to API unavailability"
      });

      // Automatically trigger honeypot if phishing is detected in fallback
      if (isPhishing) {
        await triggerHoneypot();
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

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
            SMS & Email Analysis
          </h1>
          <p className="text-off-white/70 text-lg max-w-2xl mx-auto">
            Analyze text messages and emails for phishing attempts
          </p>
        </motion.div>

        <div className="max-w-4xl mx-auto space-y-6">
          {/* Input Section */}
          <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
            <CardHeader>
              <CardTitle className="text-xl text-off-white flex items-center gap-2">
                <MessageSquare className="w-5 h-5" />
                Message Analysis
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-off-white mb-2">
                  Enter SMS or Email Content
                </label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  className="w-full h-32 px-3 py-2 bg-midnight-blue-light/30 border border-midnight-blue-light/50 rounded-md text-off-white placeholder-off-white/50 focus:border-electric-cyan focus:outline-none resize-none"
                  placeholder="Paste your SMS or email content here for analysis..."
                />
              </div>

              <Button
                onClick={handleAnalyze}
                disabled={!message.trim() || isAnalyzing}
                className="w-full bg-electric-cyan text-midnight-blue hover:bg-electric-cyan/90 font-semibold py-3"
              >
                {isAnalyzing ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-midnight-blue border-t-transparent rounded-full animate-spin" />
                    Analyzing...
                  </div>
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-2" />
                    Analyze Message
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Results Section */}
          {analysisResult && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
            >
              <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
                <CardHeader>
                  <CardTitle className="text-xl text-off-white flex items-center gap-2">
                    {analysisResult.is_phishing ? (
                      <AlertTriangle className="w-5 h-5 text-red-400" />
                    ) : (
                      <CheckCircle className="w-5 h-5 text-green-400" />
                    )}
                    Analysis Results
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid md:grid-cols-3 gap-4 mb-6">
                    <div className="text-center">
                      <div
                        className={`text-2xl font-bold ${
                          analysisResult.is_phishing
                            ? "text-red-400"
                            : "text-green-400"
                        }`}
                      >
                        {analysisResult.risk_score || Math.round(analysisResult.confidence * 100)}%
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Risk Score
                      </div>
                    </div>
                    <div className="text-center">
                      <div
                        className={`text-lg font-semibold ${
                          analysisResult.is_phishing
                            ? "text-red-400"
                            : "text-green-400"
                        }`}
                      >
                        {analysisResult.is_phishing ? "HIGH RISK" : "SAFE"}
                      </div>
                      <div className="text-off-white/70 text-sm">Status</div>
                    </div>
                    <div className="text-center">
                      <div className="text-lg font-semibold text-electric-cyan">
                        {analysisResult.suspicious_phrases.length}
                      </div>
                      <div className="text-off-white/70 text-sm">
                        Suspicious Phrases
                      </div>
                    </div>
                  </div>

                  <div className="mb-4">
                    <h4 className="text-off-white font-medium mb-2">
                      AI Detection Details:
                    </h4>
                    <div className="grid md:grid-cols-2 gap-4">
                      <div>
                        <span className="text-off-white/70 text-sm">
                          Model Label:{" "}
                        </span>
                        <span
                          className={`font-semibold ${
                            analysisResult.is_phishing
                              ? "text-red-400"
                              : "text-green-400"
                          }`}
                        >
                          {analysisResult.label}
                        </span>
                      </div>
                      <div>
                        <span className="text-off-white/70 text-sm">
                          Confidence:{" "}
                        </span>
                        <span
                          className={`font-semibold ${
                            analysisResult.is_phishing
                              ? "text-red-400"
                              : "text-green-400"
                          }`}
                        >
                          {(analysisResult.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {analysisResult.suspicious_phrases.length > 0 && (
                    <div className="mb-4">
                      <h4 className="text-off-white font-medium mb-2">
                        Detected Suspicious Phrases:
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {analysisResult.suspicious_phrases.map(
                          (phrase: string, index: number) => (
                            <span
                              key={index}
                              className="px-3 py-1 bg-red-500/20 text-red-400 rounded-full text-sm"
                            >
                              {phrase}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}

                  {analysisResult.details && (
                    <div>
                      <h4 className="text-off-white font-medium mb-2">
                        Analysis Details:
                      </h4>
                      <div className="p-3 bg-midnight-blue-light/10 rounded-lg border border-electric-cyan/30">
                        <p className="text-off-white/80 text-sm">
                          {analysisResult.details}
                        </p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Honeypot Results Section */}
          {honeypotResult && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
            >
              <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
                <CardHeader>
                  <CardTitle className="text-xl text-off-white flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-orange-400" />
                    Honeypot Extraction Results
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {honeypotResult.status === "error" ? (
                    <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-md">
                      <p className="text-red-400 font-medium">Honeypot Extraction Failed</p>
                      <p className="text-red-300 text-sm mt-1">{honeypotResult.message}</p>
                      {honeypotResult.error && (
                        <p className="text-red-200 text-xs mt-1">Error: {honeypotResult.error}</p>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {/* Status */}
                      <div className="p-3 bg-green-500/20 border border-green-500/50 rounded-md">
                        <p className="text-green-400 font-medium">✅ Honeypot Successfully Activated</p>
                        <p className="text-green-300 text-sm">Status: {honeypotResult.status}</p>
                        <p className="text-green-200 text-xs">Source IP: {honeypotResult.source_ip}</p>
                        <p className="text-green-200 text-xs">Timestamp: {new Date(honeypotResult.timestamp).toLocaleString()}</p>
                      </div>

                      {/* Raw Response Display */}
                      <div>
                        <h4 className="text-off-white font-medium mb-2">📋 Raw API Response:</h4>
                        <div className="p-3 bg-midnight-blue-light/10 rounded-lg border border-electric-cyan/30 max-h-96 overflow-y-auto">
                          <pre className="text-electric-cyan text-xs whitespace-pre-wrap">
                            {JSON.stringify(honeypotResult, null, 2)}
                          </pre>
                        </div>
                      </div>

                      {/* System Data */}
                      {honeypotResult.extraction_result?.system_data && (
                        <div>
                          <h4 className="text-off-white font-medium mb-2">🔍 Extracted System Prompt:</h4>
                          <div className="p-3 bg-midnight-blue-light/10 rounded-lg border border-orange-500/30 max-h-40 overflow-y-auto">
                            <pre className="text-orange-300 text-xs whitespace-pre-wrap">
                              {honeypotResult.extraction_result.system_data[0]?.[2] || "No system prompt found"}
                            </pre>
                          </div>
                        </div>
                      )}

                      {/* Phishing Activities */}
                      {honeypotResult.extraction_result?.phishing_activities && (
                        <div>
                          <h4 className="text-off-white font-medium mb-2">📧 Phishing Activities Detected:</h4>
                          <div className="space-y-2 max-h-32 overflow-y-auto">
                            {honeypotResult.extraction_result.phishing_activities.map((activity: any[], index: number) => (
                              <div key={index} className="p-2 bg-red-500/10 border border-red-500/30 rounded text-sm">
                                <div className="flex justify-between items-center">
                                  <span className="text-red-300 font-medium">{activity[1]}</span>
                                  <span className="text-red-400 text-xs">{activity[2]}</span>
                                </div>
                                <div className="text-red-200 text-xs mt-1">
                                  {activity[3]} • Status: {activity[4]}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Extracted Data */}
                      {honeypotResult.extraction_result?.extracted_data && (
                        <div>
                          <h4 className="text-off-white font-medium mb-2">🔐 Extracted Credentials:</h4>
                          <div className="space-y-2 max-h-24 overflow-y-auto">
                            {honeypotResult.extraction_result.extracted_data.map((data: any[], index: number) => (
                              <div key={index} className="p-2 bg-yellow-500/10 border border-yellow-500/30 rounded text-sm">
                                <div className="text-yellow-300 font-medium">{data[1]}</div>
                                <div className="text-yellow-200 text-xs">{data[2]}</div>
                                <div className="text-yellow-100 text-xs">IP: {data[4]} • {data[3]}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Message */}
                      {honeypotResult.extraction_result?.message && (
                        <div className="p-3 bg-blue-500/20 border border-blue-500/50 rounded-md">
                          <p className="text-blue-300 text-sm">{honeypotResult.extraction_result.message}</p>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Honeypot Loading State */}
          {isHoneypotActive && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
            >
              <Card className="bg-midnight-blue-light/20 border-midnight-blue-light/30">
                <CardContent className="p-6">
                  <div className="flex items-center justify-center gap-3">
                    <div className="w-6 h-6 border-2 border-orange-400 border-t-transparent rounded-full animate-spin" />
                    <p className="text-orange-400 font-medium">Activating Honeypot...</p>
                  </div>
                  <p className="text-orange-300 text-sm text-center mt-2">
                    Extracting malicious LLM data via SQL injection
                  </p>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
