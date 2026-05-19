// main.js — Spendly front-end scripts

// ------------------------------------------------------------------ //
// Video modal                                                         //
// ------------------------------------------------------------------ //

(function () {
  var overlay = document.getElementById('video-modal');
  if (!overlay) return;            // only runs on pages that have the modal

  var box     = overlay.querySelector('.vmodal-box');
  var closeBtn = document.getElementById('vmodal-close');
  var iframe  = document.getElementById('vmodal-iframe');
  var openBtn = document.getElementById('watch-btn');

  /** Open the modal and start the video */
  function openModal() {
    // Load the video only when the modal is first opened
    if (!iframe.src || iframe.src === window.location.href) {
      iframe.src = iframe.dataset.src;
    }
    overlay.removeAttribute('hidden');
    // Trigger CSS transition on next paint
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        overlay.classList.add('vmodal-visible');
      });
    });
    document.body.style.overflow = 'hidden';   // prevent background scroll
    closeBtn.focus();
  }

  /** Close the modal and stop the video */
  function closeModal() {
    overlay.classList.remove('vmodal-visible');
    // Wait for the fade-out transition before hiding the element
    overlay.addEventListener('transitionend', function handler() {
      overlay.setAttribute('hidden', '');
      // Reset src to stop playback — most reliable cross-browser approach
      iframe.src = '';
      overlay.removeEventListener('transitionend', handler);
    });
    document.body.style.overflow = '';
    if (openBtn) openBtn.focus();
  }

  // Wire up trigger
  if (openBtn) {
    openBtn.addEventListener('click', openModal);
  }

  // Close button
  closeBtn.addEventListener('click', closeModal);

  // Click on backdrop (outside the box) closes the modal
  overlay.addEventListener('click', function (e) {
    if (!box.contains(e.target)) {
      closeModal();
    }
  });

  // Escape key closes the modal
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !overlay.hasAttribute('hidden')) {
      closeModal();
    }
  });
}());
