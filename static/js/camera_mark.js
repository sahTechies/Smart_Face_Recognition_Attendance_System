// camera_mark.js
const startMarkBtn = document.getElementById("startMarkBtn");
const stopMarkBtn = document.getElementById("stopMarkBtn");
const markVideo = document.getElementById("markVideo");
const markStatus = document.getElementById("markStatus");
const recognizedList = document.getElementById("recognizedList");
const attendanceDate = document.getElementById("attendanceDate");
const selectedDateDisplay = document.getElementById("selectedDateDisplay");

let markStream = null;
let markInterval = null;
let recognizedIds = new Set();

// Initialize date inputs
document.addEventListener('DOMContentLoaded', function() {
  // Set max date to today
  const today = new Date().toISOString().split('T')[0];
  attendanceDate.max = today;
  attendanceDate.value = today;
  updateDateDisplay();
});

// Update date display when date changes
attendanceDate.addEventListener('change', updateDateDisplay);

function updateDateDisplay() {
  const selectedDate = attendanceDate.value;
  const today = new Date().toISOString().split('T')[0];
  
  if (selectedDate === today) {
    selectedDateDisplay.textContent = 'Today';
  } else {
    const dateObj = new Date(selectedDate + 'T00:00:00');
    selectedDateDisplay.textContent = dateObj.toLocaleDateString('en-US', { 
      weekday: 'short', 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric' 
    });
  }
}

function getSelectedDateString() {
  return attendanceDate.value;
}

startMarkBtn.addEventListener("click", async () => {
  startMarkBtn.disabled = true;
  stopMarkBtn.disabled = false;
  try {
    markStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    markVideo.srcObject = markStream;
    await markVideo.play();
    markStatus.innerText = "Scanning...";
    markInterval = setInterval(captureAndRecognize, 1200);
  } catch (err) {
    alert("Camera error: " + err.message);
    startMarkBtn.disabled = false;
    stopMarkBtn.disabled = true;
  }
});

stopMarkBtn.addEventListener("click", () => {
  if (markInterval) clearInterval(markInterval);
  if (markStream) markStream.getTracks().forEach(t => t.stop());
  startMarkBtn.disabled = false;
  stopMarkBtn.disabled = true;
  markStatus.innerText = "Stopped";
});

async function captureAndRecognize() {
  const canvas = document.createElement("canvas");
  canvas.width = markVideo.videoWidth || 640;
  canvas.height = markVideo.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(markVideo, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.85));
  const fd = new FormData();
  fd.append("image", blob, "snap.jpg");
  fd.append("attendance_date", getSelectedDateString());
  try {
    const res = await fetch("/recognize_face", { method: "POST", body: fd });
    const j = await res.json();
    if (j.recognized) {
      markStatus.innerText = `Recognized: ${j.name} (conf ${Math.round(j.confidence*100)}%)`;
      if (!recognizedIds.has(j.student_id)) {
        recognizedIds.add(j.student_id);
        const li = document.createElement("li");
        li.className = "list-group-item";
        const selectedDate = getSelectedDateString();
        const dateLabel = selectedDate === new Date().toISOString().split('T')[0] ? 'Today' : selectedDate;
        li.innerText = `${j.name} — ${dateLabel} — ${new Date().toLocaleTimeString()}`;
        recognizedList.prepend(li);
      }
    } else {
      if (j.error) markStatus.innerText = `Not recognized: ${j.error}`;
      else markStatus.innerText = `Not recognized`;
    }
  } catch (err) {
    console.error(err);
  }
}
