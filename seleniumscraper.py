import os
import random

import time
import json
import undetected_geckodriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile

# (Re-use or import the `make_stealth_firefox_profile` function from above.)

def make_stealth_firefox_profile(proxy: str = None) -> FirefoxProfile:
    """
    Returns a FirefoxProfile that:
      - Disables webdriver flag
      - Sets a randomized user-agent
      - Applies typical stealth prefs
      - (Optionally) configures an HTTP(S) proxy if provided
    """
    # ── 1. Create a brand-new temporary profile directory ──
    profile = FirefoxProfile()
    profile.set_preference("dom.webdriver.enabled", False)  # hides "navigator.webdriver"
    profile.set_preference("useAutomationExtension", False)
    profile.set_preference("media.navigator.enabled", True)
    profile.set_preference("media.peerconnection.ice.default_address_only", False)
    profile.set_preference("general.useragent.override", random_user_agent())
    profile.set_preference("dom.webnotifications.enabled", False)
    profile.set_preference("permissions.default.stylesheet", 2)  # disable CSS (optional)
    profile.set_preference("permissions.default.image", 2)       # disable images (speeds up scraping)
    profile.set_preference("privacy.firstparty.isolate", True)
    profile.set_preference("network.http.referer.spoofSource", True)
    profile.set_preference("browser.cache.disk.enable", False)
    profile.set_preference("browser.cache.memory.enable", False)
    profile.set_preference("browser.cache.offline.enable", False)
    profile.set_preference("network.cookie.cookieBehavior", 1)   # block third-party cookies

    # ── 2. (Optional) Configure HTTP(S) proxy if passed, e.g. "http://1.2.3.4:3128"
    if proxy:
        # This makes Firefox use that proxy for HTTP + HTTPS.
        profile.set_preference("network.proxy.type", 1)
        proto, address = proxy.split("://")
        host, port = address.split(":")
        if proto.lower() == "http":
            profile.set_preference("network.proxy.http", host)
            profile.set_preference("network.proxy.http_port", int(port))
            profile.set_preference("network.proxy.ssl", host)
            profile.set_preference("network.proxy.ssl_port", int(port))
        elif proto.lower() == "socks5":
            profile.set_preference("network.proxy.socks", host)
            profile.set_preference("network.proxy.socks_port", int(port))
            profile.set_preference("network.proxy.socks_version", 5)
        profile.set_preference("network.proxy.no_proxies_on", "")  # use proxy for all hosts

    # ── 3. Return the custom profile ──
    return profile

def random_user_agent() -> str:
    """
    Returns a semi-random desktop Firefox user-agent string.
    Real-world UAs often look like:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:▢▢.0) Gecko/▢▢▢▢▢▢ Firefox/▢▢.0"
    We can pick a random Windows version and random Firefox version to rotate.
    """
    windows_versions = [
        "Windows NT 10.0; Win64; x64",
        "Windows NT 10.0; WOW64",
        "Windows NT 6.1; Win64; x64; rv:91.0",
        "Windows NT 6.1; WOW64",
    ]
    fx_versions = ["112.0", "113.0", "114.0", "115.0", "116.0"]
    win = random.choice(windows_versions)
    fx = random.choice(fx_versions)
    rv = fx  # keep the rv: field in sync with the Fx version for realism

    return f"Mozilla/5.0 ({win}; rv:{rv}) Gecko/20100101 Firefox/{fx}"

def create_stealth_firefox_driver(proxy: str = None, headless: bool = False):
    """
    Launches a geckodriver-based Selenium WebDriver with:
      • a stealthy Firefox profile
      • optional proxy
      • optional headless mode (set to False if you want to see the browser)
    Returns: the `driver` object.
    """
    # ── 1. Build Firefox options ──
    options = uc.FirefoxOptions()
    options.headless = headless  # set to False if you want to watch it run
    options.set_preference("permissions.default.image", 2)         # disable images
    options.set_preference("browser.cache.disk.enable", False)    # disable disk cache
    options.set_preference("browser.cache.memory.enable", False)  # disable memory cache
    options.set_preference("browser.cache.offline.enable", False)
    options.set_preference("network.http.referer.spoofSource", True)

    # ── 2. Attach our stealth profile ──
    profile = make_stealth_firefox_profile(proxy)
    options.profile = profile

    # ── 3. Launch undetected geckodriver ──
    driver = uc.Chrome(options=options)  # despite the name, uc.Chrome() can also proxy to Firefox if you set the GECKODRIVER_PATH
    # If for some reason uc.Chrome() doesn’t find geckodriver for Firefox, you can explicitly pass:
    # driver = uc.Chrome(options=options, driver_executable_path="/usr/local/bin/geckodriver")

    # ── 4. “Poke” some JavaScript to hide the webdriver flag more thoroughly ──
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver

# Example usage:
if __name__ == "__main__":
    # If you have a rotating residential proxy, pass it here, e.g. "socks5://1.2.3.4:1080"
    driver = create_stealth_firefox_driver(proxy=None, headless=False)
    driver.set_page_load_timeout(30)

    try:
        driver.get("https://www.idealista.com/agencias-inmobiliarias/marbella-malaga/inmobiliarias")
        time.sleep(5)  # wait for initial JS to finish

        # …then scroll/extract as below…
    except Exception as e:
        print("Error loading page:", e)
        driver.quit()
        exit(1)
