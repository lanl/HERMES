# HERMES Roadmap

This document outlines the long-term goals for **HERMES**, whether or not they are currently in active development. It is intended as a reminder of the broader direction of the project and the major milestones ahead.

---

## Short-Term Goals (Near Term)

### Acquisition System Updates
- Update pydantic models with schemas for Acquisition
- Adjust acquireTpx3.py to have more of its code in seperate files that get called, instead of having so much clutter inside of it.
- Add **Zaber controller** support  
- Add **Serval** support
- Integrate **EMPIR** for both acquisition and analysis  

Specifically, we need to break the acquisition into three stages: 

- **Configure/Setup**: Create, modify, save, and load configuration schemas (Also validate!)
- **Initialize**: Initialize the current acquisition system with the verified configuration/setup schema (start serval, epics, zaber, etc)
- **Execution**: Run and monitor the acquisition system (start the run)


---

## Medium-Term Goals
- Develop a **GUI system** for HERMES  
- Expand analysis features (e.g., **nbragg**)  
- Implement **automatic sample focusing** with Zaber integration (potentially using ML)  
- Implement calibration support from **SoPhy/Accos**  
- Restructure the **unpacking process** (likely in conjunction with EMPIR work)  
- Set up **Read the Docs** to replace the manual
---

## Long-Term Goals

- **Widespread release** and collection of user feedback  
- Enable **preview images in the GUI** using `.tiff` files generated during acquisition  
