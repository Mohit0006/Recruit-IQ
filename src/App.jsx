import React, { useState, useEffect } from 'react';
import './App.css';

// 🌐 ENVIRONMENT ROUTING (GitHub Safe)
// This pulls the backend URL from your .env file. If it's missing, it defaults to your local FastAPI server.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export default function App() {
  const [availableJobs, setAvailableJobs] = useState([]);
  const [selectedRole, setSelectedRole] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [file, setFile] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState({ message: '', type: '' });

  // 1. Fetch available jobs from FastAPI on load
  useEffect(() => {
    async function fetchJobs() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/jobs`);
        if (!res.ok) throw new Error('Network response not ok');
        const data = await res.json();
        setAvailableJobs(data.jobs || []);
      } catch (err) {
        setStatus({ message: `⚠️ Could not connect to backend at ${API_BASE_URL}. Ensure FastAPI is running.`, type: 'error' });
      }
    }
    fetchJobs();
  }, []);

  const selectedJob = availableJobs.find((j) => j.title === selectedRole);

  // 2. Submit form with Multipart payload
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!fullName || !email || !selectedRole || !file) {
      setStatus({ message: '⚠️ Please fill out all required fields.', type: 'error' });
      return;
    }

    setIsSubmitting(true);
    setStatus({ message: '⏳ Submitting application and uploading resume... Please wait.', type: 'loading' });

    // UX Enhancement: Artificial processing delay (Optional, but looks nice for applicants)
    await new Promise((resolve) => setTimeout(resolve, 3000));

    const formData = new FormData();
    formData.append('full_name', fullName);
    formData.append('email', email);
    formData.append('role', selectedRole);
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/apply`, {
        method: 'POST',
        body: formData,
      });
      const result = await res.json();

      if (res.ok) {
        setStatus({ message: `🎉 ${result.message || 'Application submitted successfully!'}`, type: 'success' });
        setFullName('');
        setEmail('');
        setSelectedRole('');
        setFile(null);
        const fileInput = document.getElementById('resume-file');
        if (fileInput) fileInput.value = '';
      } else {
        setStatus({ message: `❌ ${result.error || 'Submission failed.'}`, type: 'error' });
      }
    } catch (err) {
      setStatus({ message: `❌ Cannot connect to backend server at ${API_BASE_URL}`, type: 'error' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container">
      <h2>🚀 Join Our Engineering Team</h2>
      <p className="subtitle">Select an open role and submit your resume to enter the screening pipeline.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="role">Applied Role <span className="req">*</span></label>
          <select
            id="role"
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            disabled={availableJobs.length === 0}
            required
          >
            <option value="">
              {availableJobs.length === 0 ? 'Loading positions...' : '-- Select a Role --'}
            </option>
            {availableJobs.map((job, idx) => (
              <option key={idx} value={job.title}>{job.title}</option>
            ))}
          </select>
        </div>

        {selectedJob && (
          <div id="job-desc-box">
            <h4>📄 {selectedJob.title}</h4>
            <p>{selectedJob.description}</p>
          </div>
        )}

        <div className="form-group">
          <label htmlFor="name">Full Legal Name <span className="req">*</span></label>
          <input
            type="text"
            id="name"
            placeholder="e.g. Rahul Sharma"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="email">Email Address <span className="req">*</span></label>
          <input
            type="email"
            id="email"
            placeholder="name@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>Upload Resume (PDF only) <span className="req">*</span></label>
          <div className="file-upload">
            <input
              type="file"
              id="resume-file"
              accept=".pdf"
              onChange={(e) => setFile(e.target.files[0])}
              required
            />
          </div>
        </div>

        <button type="submit" disabled={isSubmitting || availableJobs.length === 0}>
          {isSubmitting ? 'Processing...' : 'Submit Application'}
        </button>
      </form>

      {status.message && (
        <div className={`status-msg status-${status.type}`}>
          {status.message}
        </div>
      )}
    </div>
  );
}
