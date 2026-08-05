# add.js — verification checklist

| Input | Expected | Purpose |
|---|---|---|
| `add(2, 3)` | `5` | Happy path |
| `add(-1, 1)` | `0` | Negative + positive |
| `add(0, 0)` | `0` | Boundary: zeros |

Manual check:
```
node -e "console.log(require('./src/week-03/add.js').add(2,3))"
```
Expected output: `5`
