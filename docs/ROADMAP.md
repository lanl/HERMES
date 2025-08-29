# HERMES Roadmap

This document outlines the long-term goals for **HERMES**, whether or not they are currently in active development. It is intended as a reminder of the broader direction of the project and the major milestones ahead.

---

## Short-Term Goals (Near Term)

- Add **Zaber controller** support  
- Add **Serval** support  
- Implement calibration support from **SoPhy/Accos**  
- Integrate **EMPIR** for both acquisition and analysis  
- Restructure the **unpacking process** (likely in conjunction with EMPIR work)  
- Set up **Read the Docs** to replace the manual
- Adjust acquireTpx3.py to have more of its code in seperate files that get called, instead of having so much clutter inside of it.
- Adjust __init__.py to create an API of sorts? I'm not sure familiar with this, but it would allow for functions like """import hermes""" and """hermes.acquire_data()""" instead of the long strings that we have now.


---

## Medium-Term Goals

- Develop a **GUI system** for HERMES  
- Expand analysis features (e.g., **nbragg**)  
- Implement **automatic sample focusing** with Zaber integration (potentially using ML)  

---

## Long-Term Goals

- **Widespread release** and collection of user feedback  
- Enable **preview images in the GUI** using `.tiff` files generated during acquisition  
