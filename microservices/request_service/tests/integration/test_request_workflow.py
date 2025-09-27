"""
Integration tests for Request Service workflows
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Request, RequestStatus, RequestComment, RequestRating
from tests.conftest import RequestFactory


@pytest.mark.integration
class TestRequestWorkflowIntegration:
    """Test complete request workflows end-to-end"""

    @pytest.mark.asyncio
    async def test_complete_request_lifecycle(self, test_client: AsyncClient, test_db_session: AsyncSession):
        """Test complete request lifecycle from creation to completion"""

        # 1. Create request
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-TEST"):

            request_data = RequestFactory.create_request_data(
                title="Integration Test Request",
                description="Full workflow integration test",
                category="сантехника",
                priority="высокий"
            )

            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            assert create_response.status_code == 201

            request_number = create_response.json()["request_number"]
            assert request_number == "250927-TEST"

        # 2. Verify request exists in database
        from sqlalchemy import select
        query = select(Request).where(Request.request_number == request_number)
        result = await test_db_session.execute(query)
        db_request = result.scalar_one_or_none()

        assert db_request is not None
        assert db_request.status == RequestStatus.NEW
        assert db_request.title == "Integration Test Request"

        # 3. Add initial comment
        comment_data = RequestFactory.create_comment_data(
            comment_text="Заявка принята в работу",
            author_user_id="manager_123"
        )

        comment_response = await test_client.post(
            f"/api/v1/requests/{request_number}/comments/",
            json=comment_data
        )
        assert comment_response.status_code == 201

        # 4. Assign executor
        assignment_data = RequestFactory.create_assignment_data(
            assigned_to="executor_456",
            assignment_reason="Специалист по сантехнике"
        )

        assign_response = await test_client.post(
            f"/api/v1/requests/{request_number}/assign",
            json=assignment_data,
            params={"assigned_by": "manager_123"}
        )
        assert assign_response.status_code == 200

        # 5. Update status to in progress
        status_data = {
            "status": "в работе",
            "comment": "Исполнитель приступил к работе",
            "user_id": "executor_456"
        }

        status_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=status_data
        )
        assert status_response.status_code == 200

        # 6. Add materials request
        material_data = RequestFactory.create_material_data(
            material_name="Труба ПВХ 32мм",
            quantity=5.0,
            unit="м",
            unit_price=150.00
        )

        material_response = await test_client.post(
            f"/api/v1/requests/{request_number}/materials/",
            json=material_data
        )
        assert material_response.status_code == 201

        # 7. Update status to materials requested
        materials_status_data = {
            "status": "заказаны материалы",
            "comment": "Материалы заказаны у поставщика",
            "user_id": "executor_456"
        }

        materials_status_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=materials_status_data
        )
        assert materials_status_response.status_code == 200

        # 8. Mark materials as delivered
        delivered_status_data = {
            "status": "материалы доставлены",
            "comment": "Материалы получены",
            "user_id": "executor_456"
        }

        delivered_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=delivered_status_data
        )
        assert delivered_response.status_code == 200

        # 9. Complete the work
        completion_data = {
            "title": "Integration Test Request",
            "description": "Full workflow integration test",
            "completion_notes": "Работа выполнена качественно",
            "work_duration_minutes": 120
        }

        completion_response = await test_client.put(
            f"/api/v1/requests/{request_number}",
            json=completion_data
        )
        assert completion_response.status_code == 200

        # 10. Update status to completed
        completed_status_data = {
            "status": "выполнена",
            "comment": "Работа завершена успешно",
            "user_id": "executor_456"
        }

        completed_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=completed_status_data
        )
        assert completed_response.status_code == 200

        # 11. Add customer rating
        rating_data = RequestFactory.create_rating_data(
            rating=5,
            feedback="Отличная работа! Быстро и качественно!",
            author_user_id="applicant_789"
        )

        rating_response = await test_client.post(
            f"/api/v1/requests/{request_number}/ratings/",
            json=rating_data
        )
        assert rating_response.status_code == 201

        # 12. Verify final state
        final_response = await test_client.get(f"/api/v1/requests/{request_number}")
        assert final_response.status_code == 200

        final_data = final_response.json()
        assert final_data["status"] == "выполнена"
        assert final_data["completion_notes"] == "Работа выполнена качественно"
        assert final_data["work_duration_minutes"] == 120

        # 13. Verify comments were created
        comments_response = await test_client.get(f"/api/v1/requests/{request_number}/comments/")
        assert comments_response.status_code == 200

        comments_data = comments_response.json()
        assert len(comments_data) >= 5  # Initial comment + status change comments

        # 14. Verify rating was added
        ratings_response = await test_client.get(f"/api/v1/requests/{request_number}/ratings/")
        assert ratings_response.status_code == 200

        ratings_data = ratings_response.json()
        assert len(ratings_data) == 1
        assert ratings_data[0]["rating"] == 5

        # 15. Check database consistency
        await test_db_session.refresh(db_request)
        assert db_request.status == RequestStatus.COMPLETED
        assert db_request.completion_notes == "Работа выполнена качественно"
        assert db_request.work_duration_minutes == 120

    @pytest.mark.asyncio
    async def test_request_cancellation_workflow(self, test_client: AsyncClient):
        """Test request cancellation workflow"""

        # 1. Create request
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-CANCEL"):

            request_data = RequestFactory.create_request_data(
                title="Request to Cancel",
                description="This request will be cancelled"
            )

            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            assert create_response.status_code == 201
            request_number = create_response.json()["request_number"]

        # 2. Add cancellation comment
        cancel_comment_data = RequestFactory.create_comment_data(
            comment_text="Заявка отменена по просьбе заявителя",
            author_user_id="manager_123"
        )

        comment_response = await test_client.post(
            f"/api/v1/requests/{request_number}/comments/",
            json=cancel_comment_data
        )
        assert comment_response.status_code == 201

        # 3. Update status to cancelled
        cancel_status_data = {
            "status": "отменена",
            "comment": "Заявка отменена",
            "user_id": "manager_123"
        }

        cancel_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=cancel_status_data
        )
        assert cancel_response.status_code == 200

        # 4. Verify final state
        final_response = await test_client.get(f"/api/v1/requests/{request_number}")
        assert final_response.status_code == 200

        final_data = final_response.json()
        assert final_data["status"] == "отменена"

    @pytest.mark.asyncio
    async def test_ai_assisted_assignment_workflow(self, test_client: AsyncClient):
        """Test AI-assisted assignment workflow"""

        # 1. Create request
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-AI"):

            request_data = RequestFactory.create_request_data(
                title="AI Assignment Test",
                category="электрика",
                priority="срочный"
            )

            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            assert create_response.status_code == 201
            request_number = create_response.json()["request_number"]

        # 2. Get AI optimization suggestions
        optimize_data = {
            "request_number": request_number,
            "max_suggestions": 3,
            "algorithm": "greedy"
        }

        with patch('app.services.ai_service.AIService.get_smart_assignment_suggestions') as mock_ai:
            mock_optimization_result = type('OptimizationResult', (), {
                'suggestions': [
                    type('Suggestion', (), {
                        'executor_user_id': 'ai_executor_001',
                        'confidence_score': 0.92,
                        'reasoning': 'Excellent electrical skills match',
                        'estimated_completion_time': 3.5,
                        'cost_efficiency_score': 0.88,
                        'geographic_score': 0.95,
                        'workload_score': 0.90,
                        'specialization_score': 0.95
                    })()
                ],
                'algorithm_used': 'greedy',
                'execution_time_ms': 120.0,
                'optimization_score': 0.92,
                'metadata': {'source': 'local_optimization', 'executor_count': 5}
            })()

            mock_ai.return_value = mock_optimization_result

            optimize_response = await test_client.post("/api/v1/ai/optimize", json=optimize_data)
            assert optimize_response.status_code == 200

            suggestions = optimize_response.json()["suggestions"]
            assert len(suggestions) == 1
            best_executor = suggestions[0]["executor_user_id"]

        # 3. Use AI suggestion for assignment
        assignment_data = RequestFactory.create_assignment_data(
            assigned_to=best_executor,
            assignment_type="ai_recommended",
            assignment_reason="AI recommendation: Excellent electrical skills match"
        )

        assign_response = await test_client.post(
            f"/api/v1/requests/{request_number}/assign",
            json=assignment_data,
            params={"assigned_by": "ai_dispatcher"}
        )
        assert assign_response.status_code == 200

        # 4. Verify assignment
        final_response = await test_client.get(f"/api/v1/requests/{request_number}")
        assert final_response.status_code == 200

        final_data = final_response.json()
        assert final_data["executor_user_id"] == best_executor

    @pytest.mark.asyncio
    async def test_materials_workflow_integration(self, test_client: AsyncClient):
        """Test materials management workflow"""

        # 1. Create request
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-MAT"):

            request_data = RequestFactory.create_request_data(
                title="Materials Workflow Test",
                category="сантехника"
            )

            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            assert create_response.status_code == 201
            request_number = create_response.json()["request_number"]

        # 2. Add multiple materials
        materials = [
            RequestFactory.create_material_data(
                material_name="Труба ПВХ 32мм",
                quantity=10.0,
                unit="м",
                unit_price=150.00
            ),
            RequestFactory.create_material_data(
                material_name="Фитинг 32мм",
                quantity=5.0,
                unit="шт",
                unit_price=75.00
            ),
            RequestFactory.create_material_data(
                material_name="Герметик",
                quantity=1.0,
                unit="туба",
                unit_price=250.00
            )
        ]

        material_ids = []
        for material_data in materials:
            material_response = await test_client.post(
                f"/api/v1/requests/{request_number}/materials/",
                json=material_data
            )
            assert material_response.status_code == 201
            material_ids.append(material_response.json()["id"])

        # 3. Get materials list
        materials_list_response = await test_client.get(f"/api/v1/requests/{request_number}/materials/")
        assert materials_list_response.status_code == 200

        materials_list = materials_list_response.json()
        assert len(materials_list) == 3

        # 4. Update material status (mark as ordered)
        for material_id in material_ids:
            update_data = {
                "status": "ordered",
                "supplier": "ТехноСтрой+"
            }

            update_response = await test_client.put(
                f"/api/v1/requests/{request_number}/materials/{material_id}",
                json=update_data
            )
            assert update_response.status_code == 200

        # 5. Get cost summary
        cost_response = await test_client.get(f"/api/v1/requests/{request_number}/materials/cost-summary")
        assert cost_response.status_code == 200

        cost_data = cost_response.json()
        expected_total = (10.0 * 150.00) + (5.0 * 75.00) + (1.0 * 250.00)  # 2425.00
        assert cost_data["total_cost"] == expected_total

        # 6. Mark materials as delivered
        for material_id in material_ids:
            deliver_data = {
                "status": "delivered"
            }

            deliver_response = await test_client.put(
                f"/api/v1/requests/{request_number}/materials/{material_id}",
                json=deliver_data
            )
            assert deliver_response.status_code == 200

        # 7. Update request status
        status_data = {
            "status": "материалы доставлены",
            "comment": "Все материалы получены",
            "user_id": "executor_123"
        }

        status_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=status_data
        )
        assert status_response.status_code == 200


@pytest.mark.integration
class TestServiceIntegration:
    """Test integration between different services"""

    @pytest.mark.asyncio
    async def test_database_redis_integration(self, test_client: AsyncClient):
        """Test integration between database and Redis for request numbering"""

        # Mock Redis to simulate failure scenario
        with patch('app.services.request_number_service.RequestNumberService._generate_from_redis',
                   side_effect=Exception("Redis connection failed")), \
             patch('app.services.request_number_service.RequestNumberService._generate_from_database',
                   return_value="250927-DB1") as mock_db_fallback:

            request_data = RequestFactory.create_request_data(
                title="Database Fallback Test"
            )

            response = await test_client.post("/api/v1/requests/", json=request_data)

            assert response.status_code == 201
            data = response.json()

            # Should use database fallback
            assert data["request_number"] == "250927-DB1"
            mock_db_fallback.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_request_creation_integration(self, test_client: AsyncClient):
        """Test concurrent request creation with proper number sequencing"""
        import asyncio

        # Mock sequential request numbers
        request_numbers = ["250927-001", "250927-002", "250927-003", "250927-004", "250927-005"]

        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   side_effect=request_numbers):

            # Create multiple requests concurrently
            async def create_request(index):
                request_data = RequestFactory.create_request_data(
                    title=f"Concurrent Request {index}",
                    applicant_user_id=f"user_{index}"
                )
                return await test_client.post("/api/v1/requests/", json=request_data)

            tasks = [create_request(i) for i in range(1, 6)]
            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 201

            # Check unique request numbers
            returned_numbers = [r.json()["request_number"] for r in responses]
            assert len(set(returned_numbers)) == len(returned_numbers)  # All unique

            # Should be in expected format
            for number in returned_numbers:
                assert number in request_numbers

    @pytest.mark.asyncio
    async def test_ai_service_database_integration(self, test_client: AsyncClient, sample_request: Request):
        """Test AI service integration with database queries"""

        # Test that AI optimization works with real database data
        optimize_data = {
            "request_number": sample_request.request_number,
            "max_suggestions": 3
        }

        # Don't mock the AI service to test real integration
        response = await test_client.post("/api/v1/ai/optimize", json=optimize_data)

        # Should work even with mock executors
        assert response.status_code == 200
        data = response.json()

        assert data["request_number"] == sample_request.request_number
        assert "suggestions" in data
        assert "algorithm_used" in data

    @pytest.mark.asyncio
    async def test_search_analytics_integration(self, test_client: AsyncClient, sample_request: Request):
        """Test search and analytics integration with real data"""

        # 1. Create additional test data
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   side_effect=["250927-S01", "250927-S02"]):

            for i in range(2):
                request_data = RequestFactory.create_request_data(
                    title=f"Search Test Request {i+1}",
                    category="электрика",
                    priority="высокий"
                )
                create_response = await test_client.post("/api/v1/requests/", json=request_data)
                assert create_response.status_code == 201

        # 2. Test search functionality
        search_response = await test_client.get(
            "/api/v1/requests/search",
            params={
                "category": "электрика",
                "priority": "высокий",
                "limit": 10
            }
        )
        assert search_response.status_code == 200

        search_data = search_response.json()
        assert search_data["total"] >= 2  # Should find our test requests

        # 3. Test analytics with the same data
        analytics_response = await test_client.get("/api/v1/requests/analytics/overview")
        assert analytics_response.status_code == 200

        analytics_data = analytics_response.json()
        assert analytics_data["volume_metrics"]["total_requests"] >= 3  # Original + 2 new

        # 4. Test export functionality
        export_response = await test_client.get(
            "/api/v1/requests/export/json",
            params={"category": "электрика"}
        )
        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "application/json"


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Test error handling across integrated services"""

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, test_client: AsyncClient):
        """Test transaction rollback on service errors"""

        request_data = RequestFactory.create_request_data()

        # Mock a scenario where request creation starts but fails during processing
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-ERR"), \
             patch('app.models.Request.__init__', side_effect=Exception("Database error")):

            response = await test_client.post("/api/v1/requests/", json=request_data)

            assert response.status_code == 500

            # Verify the request wasn't partially created
            get_response = await test_client.get("/api/v1/requests/250927-ERR")
            assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_cascading_failure_handling(self, test_client: AsyncClient, sample_request: Request):
        """Test handling of cascading service failures"""

        # Test scenario where AI service fails but system continues
        optimize_data = {
            "request_number": sample_request.request_number,
            "max_suggestions": 3
        }

        with patch('app.services.ai_service.AIService._get_ai_service_suggestions',
                   side_effect=Exception("External AI service down")):

            # Should fallback to local algorithms
            response = await test_client.post("/api/v1/ai/optimize", json=optimize_data)

            assert response.status_code == 200  # Should still work with fallback
            data = response.json()

            # Should use local algorithm
            assert data["algorithm_used"] in ["greedy", "genetic", "simulated_annealing", "hybrid"]