// Color Animals — scene test
// Plays a line-art creature video (WebM with alpha, exterior transparent),
// tints the white interior with the visitor's chosen color via canvas
// multiply-blend, then restores the alpha mask so the scene bg shows through.

const video = document.getElementById('src');
const canvas = document.getElementById('stage');
const ctx = canvas.getContext('2d');
const picker = document.getElementById('picker');
const presets = document.querySelectorAll('.swatch');
const status = document.getElementById('status');

let visitorColor = picker.value;

picker.addEventListener('input', (e) => {
  visitorColor = e.target.value;
  presets.forEach((s) => s.classList.toggle('active', s.dataset.color === visitorColor));
});

presets.forEach((sw) => {
  sw.addEventListener('click', () => {
    visitorColor = sw.dataset.color;
    picker.value = visitorColor;
    presets.forEach((s) => s.classList.toggle('active', s === sw));
  });
});

video.addEventListener('loadedmetadata', () => {
  status.textContent = `loaded · ${video.videoWidth}x${video.videoHeight}`;
});
video.addEventListener('error', () => {
  status.textContent = 'video failed to load';
});

function fitRect(vw, vh, cw, ch) {
  const scale = Math.min(cw / vw, ch / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  return {
    dx: (cw - dw) / 2,
    dy: (ch - dh) / 2,
    dw,
    dh,
  };
}

function render() {
  if (video.readyState >= 2 && video.videoWidth) {
    const { dx, dy, dw, dh } = fitRect(video.videoWidth, video.videoHeight, canvas.width, canvas.height);

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Draw the line-art video (alpha preserved → exterior bg is transparent)
    ctx.drawImage(video, dx, dy, dw, dh);

    // 2. Multiply with the visitor color so black lines stay black and white
    //    interior becomes the tint color
    ctx.globalCompositeOperation = 'multiply';
    ctx.fillStyle = visitorColor;
    ctx.fillRect(dx, dy, dw, dh);

    // 3. Re-apply the video's alpha mask so the multiply step can't leak the
    //    fill color into the originally-transparent exterior region
    ctx.globalCompositeOperation = 'destination-in';
    ctx.drawImage(video, dx, dy, dw, dh);

    ctx.globalCompositeOperation = 'source-over';
  }
  requestAnimationFrame(render);
}

render();
