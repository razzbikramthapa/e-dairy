document.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('header');
  const menuToggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('nav');
  const navLinks = document.querySelectorAll('nav a');

  // Handle header background change on scroll
  window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  });

  // Mobile navigation menu toggle
  if (menuToggle && nav) {
    menuToggle.addEventListener('click', () => {
      nav.classList.toggle('active');
      
      const spans = menuToggle.querySelectorAll('span');
      if (nav.classList.contains('active')) {
        spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
        spans[1].style.opacity = '0';
        spans[2].style.transform = 'rotate(-45deg) translate(6px, -6px)';
      } else {
        spans[0].style.transform = 'none';
        spans[1].style.opacity = '1';
        spans[2].style.transform = 'none';
      }
    });
  }

  // Close mobile nav when clicking a link
  navLinks.forEach(link => {
    link.addEventListener('click', () => {
      if (nav.classList.contains('active')) {
        nav.classList.remove('active');
        const spans = menuToggle.querySelectorAll('span');
        spans[0].style.transform = 'none';
        spans[1].style.opacity = '1';
        spans[2].style.transform = 'none';
      }
    });
  });

  // Navbar authentication status check
  function updateNavbarAuth() {
    const token = localStorage.getItem('e_dairy_token');
    const userNavCta = document.querySelector('.nav-cta');
    if (!userNavCta) return;

    if (token) {
      userNavCta.innerHTML = `
        <a href="api-test.html" class="btn btn-login" style="background:var(--accent); color:var(--white);" id="btn-header-dash">Open Panel</a>
        <button class="btn btn-outline-secondary" id="btn-header-logout" style="border-radius:30px; margin-left: 12px; padding: 8px 18px; font-size:14px; font-weight:600; cursor:pointer; background:none; border:1px solid rgba(82,59,139,0.15); transition:var(--transition); color: var(--text);">Logout</button>
      `;
      
      // Hook logout listener
      document.getElementById('btn-header-logout').addEventListener('click', () => {
        localStorage.removeItem('e_dairy_token');
        localStorage.removeItem('e_dairy_user');
        localStorage.removeItem('e_dairy_role');
        
        // Restore standard Login link
        userNavCta.innerHTML = `
          <a href="login.html" class="btn btn-login" id="btn-header-login">Login</a>
        `;
      });
    }
  }

  // Run navbar check on load
  updateNavbarAuth();
});