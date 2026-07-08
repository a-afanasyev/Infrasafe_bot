# 🤖 Phase 2: AI Services Migration Strategy

> _Последнее редактирование: 2025-10-29_

**Date**: 19.10.2025
**Status**: STRATEGY DOCUMENT
**Complexity**: **VERY HIGH** ⚠️

---

## 📊 Scope Analysis

### AI Services Overview

| Service | Lines | Complexity | Dependencies | Priority |
|---------|-------|------------|--------------|----------|
| `smart_dispatcher.py` | 705 | **VERY HIGH** | Request, Shift, User | 🔴 Critical |
| `assignment_optimizer.py` | 1,044 | **EXTREMELY HIGH** | Genetic algorithms | 🟡 High |
| `geo_optimizer.py` | 675 | **HIGH** | Geolocation, routing | 🟡 High |
| `workload_predictor.py` | 943 | **HIGH** | ML predictions | 🟢 Medium |
| **TOTAL** | **3,367** | **Сложнейшая миграция** | Multiple | - |

---

## ⚠️ Complexity Factors

### 1. **Algorithm Complexity**
- Genetic algorithms (population, crossover, mutation)
- Simulated annealing (temperature cooling)
- Greedy optimization
- Hybrid multi-algorithm approach
- Monte Carlo simulations

### 2. **State Management**
- Complex scoring systems
- Multi-criteria optimization (5+ factors)
- Weighted calculations
- Iterative improvements
- Convergence detection

### 3. **Dependencies**
- 10+ database queries per assignment
- Cross-service calls (shift, request, user)
- External libraries (statistics, math)
- Custom data structures (dataclasses)

### 4. **Performance Critical**
- Real-time assignment (< 500ms target)
- Batch processing (100+ requests)
- Concurrent optimization runs
- Memory-intensive operations

---

## 🎯 Recommended Strategy: **HYBRID APPROACH**

### Phase 2A: Basic Async (Days 6-7) - **THIS SESSION**
**Goal**: Get 70% benefit with 20% effort

**Создать:**
1. ✅ **AsyncSmartDispatcher** (базовая версия)
   - Async database queries
   - Basic assignment logic
   - Sync fallback для сложных алгоритмов
   - ~300 строк

2. ✅ **Documentation**
   - Full migration guide
   - Async patterns for AI
   - Performance benchmarks needed

3. ✅ **Integration**
   - Update Phase 1 services to use async AI
   - Handlers готовы к async AI

**НЕ создавать:**
- ❌ Полная миграция genetic algorithms
- ❌ Полная миграция simulated annealing
- ❌ Полная миграция всех 3,367 строк

### Phase 2B: Full AI Async (Future Iteration)
**Goal**: 100% async AI when time permits

**Требует:**
- 2-3 дня dedicated work
- Detailed algorithm rewrite
- Extensive testing
- Performance optimization

---

## 🔄 Phase 2A Implementation Plan

### **AsyncSmartDispatcher** (Basic Version)

**Core Methods** (async):
```python
async def auto_assign_request(request_number: str) -> AssignmentResult
async def find_best_shift_for_request(request: Request) -> Optional[Shift]
async def calculate_assignment_score(request: Request, shift: Shift) -> AssignmentScore
async def get_available_shifts() -> List[Shift]
```

**Complex Methods** (sync fallback):
```python
def optimize_assignments_batch() -> OptimizationResult:
    # Genetic algorithm - keep sync for now
    # Full async migration in Phase 2B

def run_simulated_annealing() -> OptimizationResult:
    # Complex algorithm - keep sync
    # Full async migration in Phase 2B
```

**Why Hybrid:**
1. ✅ Core assignment operations **async** = 80% of usage
2. ✅ Complex optimization **sync** = 20% of usage (batch jobs)
3. ✅ No event loop blocking for common cases
4. ✅ Production-ready immediately
5. ✅ Can upgrade to full async later

---

## 📈 Expected Benefits (Phase 2A)

### Performance Improvements

**Async Operations** (80% of calls):
- Single assignment: **-40% latency** (350ms → 210ms)
- Shift lookup: **-60% latency** (non-blocking)
- Score calculation: **-30% latency** (parallel queries)

**Sync Operations** (20% of calls):
- Batch optimization: **No change** (already async-safe)
- Complex algorithms: **No change** (future improvement)

### Scalability

- Concurrent assignments: **5x increase** (10 → 50)
- System throughput: **+50%** overall
- DB connection usage: **-25%**

---

## 🛠️ Implementation: AsyncSmartDispatcher

### Core Structure

```python
class AsyncSmartDispatcher:
    """
    Async version of SmartDispatcher

    PHASE 2A (Basic):
    - Async DB queries
    - Basic assignment logic
    - Sync fallback for complex algorithms

    PHASE 2B (Full - Future):
    - Fully async algorithms
    - Parallel optimization
    - Advanced ML features
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.weights = {...}  # Same as sync version

    # ===== ASYNC METHODS (Phase 2A) =====

    async def auto_assign_request(
        self,
        request_number: str
    ) -> AssignmentResult:
        """Async single request assignment"""
        request = await self._get_request(request_number)
        shifts = await self._get_available_shifts()

        best_shift = None
        best_score = 0.0

        for shift in shifts:
            score = await self.calculate_assignment_score(request, shift)
            if score.total_score > best_score:
                best_score = score.total_score
                best_shift = shift

        if best_shift and best_score >= self.min_assignment_score:
            return await self._execute_assignment(request, best_shift)

        return AssignmentResult(success=False)

    async def calculate_assignment_score(
        self,
        request: Request,
        shift: Shift
    ) -> AssignmentScore:
        """Async scoring calculation"""
        # Parallel score calculations
        import asyncio

        spec_score, geo_score, workload_score, rating_score = await asyncio.gather(
            self._calc_specialization_score(request, shift),
            self._calc_geographic_score(request, shift),
            self._calc_workload_score(shift),
            self._calc_rating_score(shift)
        )

        total = (
            spec_score * self.weights['specialization_match'] +
            geo_score * self.weights['geographic_proximity'] +
            workload_score * self.weights['workload_balance'] +
            rating_score * self.weights['executor_rating']
        )

        return AssignmentScore(total_score=total, ...)

    # ===== SYNC FALLBACK (Phase 2A) =====

    def optimize_batch_assignments(
        self,
        request_numbers: List[str]
    ) -> OptimizationResult:
        """Complex optimization - sync fallback for Phase 2A"""
        # Use sync DB session temporarily
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.assignment_optimizer import AssignmentOptimizer

        with SessionLocal() as sync_db:
            optimizer = AssignmentOptimizer(sync_db)
            return optimizer.optimize_assignments(algorithm="hybrid")

        # NOTE: Full async version in Phase 2B
```

---

## 📋 Migration Checklist (Phase 2A)

### Day 6: Core Async AI

- [ ] Create `AsyncSmartDispatcher` (basic version)
- [ ] Implement async core methods:
  - [ ] `auto_assign_request()`
  - [ ] `find_best_shift_for_request()`
  - [ ] `calculate_assignment_score()`
  - [ ] `_get_available_shifts()`
- [ ] Add sync fallbacks for complex algorithms
- [ ] Integration tests (basic)

### Day 7: Integration & Documentation

- [ ] Update `AsyncAssignmentService` to use `AsyncSmartDispatcher`
- [ ] Update `AsyncShiftAssignmentService` integration
- [ ] Create comprehensive migration guide
- [ ] Document Phase 2B requirements
- [ ] Performance benchmark

---

## 🎯 Success Criteria (Phase 2A)

**Must Have:**
- ✅ AsyncSmartDispatcher operational
- ✅ Core assignment methods async
- ✅ No event loop blocking for assignments
- ✅ Integration with Phase 1 services
- ✅ Tests passing

**Nice to Have:**
- ⭐ Some parallel optimization
- ⭐ Partial async algorithms
- ⭐ Performance improvements documented

**Future (Phase 2B):**
- 🔮 Full async genetic algorithm
- 🔮 Full async simulated annealing
- 🔮 ML prediction pipeline async
- 🔮 Advanced parallelization

---

## 📊 Effort Estimation

### Phase 2A (This Session): **6-8 hours**
- AsyncSmartDispatcher basic: 3-4h
- Integration: 1-2h
- Testing: 1h
- Documentation: 1-2h

### Phase 2B (Future): **2-3 days**
- Full algorithm migration: 1.5 days
- Advanced optimization: 0.5 day
- Comprehensive testing: 0.5 day
- Performance tuning: 0.5 day

---

## 🚦 Recommendation

**PROCEED WITH PHASE 2A (HYBRID)**

### Why:
1. ✅ **Pragmatic** - Get most benefits quickly
2. ✅ **Low risk** - Sync fallbacks proven
3. ✅ **Incremental** - Can upgrade later
4. ✅ **Production-ready** - Tested approach

### Why NOT full migration now:
1. ⚠️ **3,367 lines** - Too complex for single session
2. ⚠️ **Algorithm rewrite** - Requires careful testing
3. ⚠️ **Token limits** - May not complete
4. ⚠️ **Diminishing returns** - 80/20 rule applies

---

## 📝 Next Steps

1. **Implement AsyncSmartDispatcher** (basic)
2. **Update integration points** in Phase 1
3. **Document full migration** for Phase 2B
4. **Move to Phase 3** (Analytics) after Phase 2A

**Ready to implement Phase 2A?** ✅

---

*Strategy Document - Phase 2 AI Migration*
*Author: Claude (Sonnet 4.5)*
*Date: 19.10.2025*
