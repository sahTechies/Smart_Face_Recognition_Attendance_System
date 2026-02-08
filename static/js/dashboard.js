// dashboard.js
document.addEventListener("DOMContentLoaded", () => {
  const trainBtn = document.getElementById("trainBtn");
  const trainProgress = document.getElementById("trainProgress");
  const trainMsg = document.getElementById("trainMsg");

  async function pollStatus() {
    try {
      const res = await fetch("/train_status");
      const data = await res.json();
      trainProgress.style.width = data.progress + "%";
      trainProgress.innerText = data.progress + "%";
      trainMsg.innerText = data.message || "";
      return data;
    } catch (e) {
      console.error(e);
      return null;
    }
  }

  trainBtn.addEventListener("click", async () => {
    trainBtn.disabled = true;
    const start = await fetch("/train_model");
    if (!start.ok && start.status !== 202) {
      alert("Failed to start training");
      trainBtn.disabled = false;
      return;
    }
    trainMsg.innerText = "Training started...";
    // poll until progress==100 or not running
    const t = setInterval(async () => {
      const s = await pollStatus();
      if (s) {
        // Check if training is complete (progress 100) or stopped (not running)
        if (s.progress >= 100 || (!s.running && s.progress > 0)) {
          clearInterval(t);
          trainBtn.disabled = false;
          if (s.progress >= 100) {
            alert("Training completed successfully!");
          } else if (s.message && (s.message.includes("error") || s.message.includes("No training") || s.message.includes("not found"))) {
            alert("Training stopped: " + s.message);
          }
        } else if (!s.running && s.progress === 0 && s.message.includes("error")) {
          clearInterval(t);
          trainBtn.disabled = false;
          alert("Training failed: " + s.message);
        }
      }
    }, 1500);
  });

  // Chart initial render & update every 10s
  let chart = null;
  async function updateChart() {
    const res = await fetch("/attendance_stats");
    const data = await res.json();
    const ctx = document.getElementById("attendanceChart").getContext("2d");
    if (!chart) {
      chart = new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.dates,
          datasets: [{ label: "Attendance", data: data.counts, backgroundColor: "rgba(59,130,246,0.7)" }]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });
    } else {
      chart.data.labels = data.dates;
      chart.data.datasets[0].data = data.counts;
      chart.update();
    }
  }
  updateChart();
  setInterval(updateChart, 10000);
});
