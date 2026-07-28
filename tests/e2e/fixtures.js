const base = require("@playwright/test");

const test = base.test.extend({
  medicationApi: async ({ request }, use) => {
    const trackedIds = new Set();

    const getPlan = async () => {
      const response = await request.get("/api/medications");
      base.expect(response.ok()).toBeTruthy();
      return response.json();
    };

    const api = {
      getPlan,

      track(id) {
        trackedIds.add(id);
      },

      async create({
        name,
        schedules,
        timingMode = "routine",
        maxAutoShiftMinutes = 120,
      }) {
        const response = await request.post("/api/medications", {
          data: {
            name,
            schedules,
            timingMode,
            maxAutoShiftMinutes,
          },
        });
        base.expect(response.status()).toBe(201);
        const payload = await response.json();
        trackedIds.add(payload.medication.id);
        return payload.medication;
      },

      async update(medication, changes = {}) {
        const response = await request.put(`/api/medications/${medication.id}`, {
          headers: { "If-Match": `"${medication.revision}"` },
          data: {
            name: changes.name ?? medication.name,
            revision: medication.revision,
            timingMode: changes.timingMode ?? medication.timingMode,
            maxAutoShiftMinutes:
              changes.maxAutoShiftMinutes ?? medication.maxAutoShiftMinutes,
            schedules: changes.schedules ?? medication.schedules,
          },
        });
        base.expect(response.ok()).toBeTruthy();
        const payload = await response.json();
        return payload.medication;
      },
    };

    await use(api);

    const plan = await getPlan();
    for (const id of Array.from(trackedIds).reverse()) {
      const medication = plan.medications.find((candidate) => candidate.id === id);
      if (!medication) continue;
      const response = await request.delete(`/api/medications/${id}`, {
        headers: { "If-Match": `"${medication.revision}"` },
      });
      base.expect(response.ok()).toBeTruthy();
    }
  },
});

module.exports = {
  expect: base.expect,
  test,
};
