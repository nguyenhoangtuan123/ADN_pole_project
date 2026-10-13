/* ==========================================================================
   nav.js – Logic điều hướng dùng chung
   - Thanh mục lục trang dashboard (IntersectionObserver)
   - Đọc tham số ?q= và điền vào ô nhập chatbot
   ========================================================================== */
(function () {
  "use strict";

  /* -------------------------------------------------------------------------
     1. Thanh mục lục (Page TOC) – chỉ chạy nếu tồn tại .page-toc trên DOM
     ----------------------------------------------------------------------- */
  var toc = document.querySelector(".page-toc");
  if (toc) {
    var tocLinks = Array.prototype.slice.call(
      toc.querySelectorAll(".page-toc__item[href^='#']")
    );

    /* Bấm vào mục: cuộn mượt tới section, có xem xét prefers-reduced-motion */
    tocLinks.forEach(function (link) {
      link.addEventListener("click", function (e) {
        var targetId = link.getAttribute("href").slice(1);
        var target = document.getElementById(targetId);
        if (!target) return;
        e.preventDefault();
        var behavior =
          window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth";
        target.scrollIntoView({ behavior: behavior, block: "start" });
        /* Đặt focus để keyboard users biết họ đang ở đâu */
        target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
      });
    });

    /* IntersectionObserver: đánh dấu mục đang xem */
    if ("IntersectionObserver" in window) {
      var sectionIds = tocLinks
        .map(function (l) {
          return l.getAttribute("href").slice(1);
        })
        .filter(Boolean);

      var sectionEls = sectionIds
        .map(function (id) {
          return document.getElementById(id);
        })
        .filter(Boolean);

      /* Lưu trữ tỷ lệ hiển thị của từng section */
      var ratioMap = {};
      sectionEls.forEach(function (el) {
        ratioMap[el.id] = 0;
      });

      function updateActiveToc() {
        /* Tìm section đang xuất hiện nhiều nhất */
        var bestId = null;
        var bestRatio = -1;
        Object.keys(ratioMap).forEach(function (id) {
          if (ratioMap[id] > bestRatio) {
            bestRatio = ratioMap[id];
            bestId = id;
          }
        });
        tocLinks.forEach(function (link) {
          var hrefId = link.getAttribute("href").slice(1);
          if (hrefId === bestId) {
            link.classList.add("page-toc__item--active");
          } else {
            link.classList.remove("page-toc__item--active");
          }
        });
      }

      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            ratioMap[entry.target.id] = entry.intersectionRatio;
          });
          updateActiveToc();
        },
        {
          root: null,
          rootMargin: "-56px 0px -20% 0px",
          threshold: [0, 0.1, 0.25, 0.5, 0.75, 1]
        }
      );

      sectionEls.forEach(function (el) {
        observer.observe(el);
      });
    }
  }

  /* -------------------------------------------------------------------------
     2. Trang chatbot: điền sẵn câu hỏi vào ô nhập (không tự gửi)
     Dùng cho tham số ?q= và các câu gợi ý ở sidebar. Không đụng vào logic chatbot:
     chỉ đặt .value rồi phát sự kiện "input" để JS gốc cập nhật bộ đếm và chiều cao.
     ----------------------------------------------------------------------- */
  var userInput = document.getElementById("user-input");

  function prefillChatInput(text) {
    if (!userInput || !text) return;
    userInput.value = String(text).trim();          // .value, không dùng innerHTML
    userInput.dispatchEvent(new Event("input", { bubbles: true }));
    userInput.focus();
  }

  if (userInput) {
    var urlParams = new URLSearchParams(window.location.search);
    var qValue = urlParams.get("q");
    if (qValue && qValue.trim().length > 0) {
      prefillChatInput(qValue);
      /* Xóa ?q khỏi URL mà không tải lại trang */
      urlParams.delete("q");
      var newSearch = urlParams.toString();
      history.replaceState(
        null,
        "",
        window.location.pathname + (newSearch ? "?" + newSearch : "") + window.location.hash
      );
    }
  }

  /* -------------------------------------------------------------------------
     3. Sidebar trang chatbot (ngăn kéo trên điện thoại < 768px)
     ----------------------------------------------------------------------- */
  var sidebar = document.getElementById("chat-sidebar");
  if (sidebar) {
    var toggleBtn = document.getElementById("btn-sidebar-toggle");
    var backdrop = document.getElementById("sidebar-backdrop");
    var desktopMq = window.matchMedia("(min-width: 768px)");

    function isOpen() {
      return sidebar.classList.contains("is-open");
    }
    function openSidebar() {
      if (desktopMq.matches) return;                 // máy tính: sidebar luôn hiện
      sidebar.classList.add("is-open");
      if (backdrop) backdrop.hidden = false;
      if (toggleBtn) {
        toggleBtn.setAttribute("aria-expanded", "true");
        toggleBtn.setAttribute("aria-label", "Đóng menu AgriBot");
      }
      var first = sidebar.querySelector("button, a");
      if (first) first.focus();
    }
    function closeSidebar(returnFocus) {
      var wasOpen = isOpen();
      sidebar.classList.remove("is-open");
      if (backdrop) backdrop.hidden = true;
      if (toggleBtn) {
        toggleBtn.setAttribute("aria-expanded", "false");
        toggleBtn.setAttribute("aria-label", "Mở menu AgriBot");
        if (wasOpen && returnFocus) toggleBtn.focus();
      }
    }

    if (toggleBtn) {
      toggleBtn.addEventListener("click", function () {
        if (isOpen()) closeSidebar(true); else openSidebar();
      });
    }
    if (backdrop) backdrop.addEventListener("click", function () { closeSidebar(true); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) closeSidebar(true);
    });
    /* Đổi kích thước lên máy tính: đóng ngăn kéo để không kẹt trạng thái */
    var onMqChange = function () { if (desktopMq.matches) closeSidebar(false); };
    if (desktopMq.addEventListener) desktopMq.addEventListener("change", onMqChange);
    else if (desktopMq.addListener) desktopMq.addListener(onMqChange);

    /* Câu gợi ý: điền vào ô nhập, người dùng tự bấm gửi */
    Array.prototype.forEach.call(sidebar.querySelectorAll(".chat-sidebar__item"), function (btn) {
      btn.addEventListener("click", function () {
        prefillChatInput(btn.getAttribute("data-q"));
        closeSidebar(false);
      });
    });

    /* "Cuộc trò chuyện mới": dùng lại nút và hộp xác nhận có sẵn của chatbot */
    var newBtn = document.getElementById("btn-sidebar-new");
    var origNewChat = document.getElementById("btn-new-chat");
    if (newBtn && origNewChat) {
      newBtn.addEventListener("click", function () {
        closeSidebar(false);
        origNewChat.click();
      });
    }
  }
})();
